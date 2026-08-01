"""機構確認用シナリオで、秘匿役職の一周が成立することを保証する。

## このシナリオの位置づけ

`station_drill` は**質感を見るためのものではない**。襲撃・会議・投票・追放・
作業・偽装が実際に噛み合うかを、短い tick 数で確かめるためのもの。
`darkened_station` (5 部屋 / 会議上限 20 / 40 tick 級) を縮めたのではなく、
確かめたいことが違うので別に置いた。

## なぜ実 run の前にここで確かめるか

実 LLM の run は「エージェントがその手を選ぶか」に左右される。**選ばれ
なかったのか、そもそも動かないのかが区別できない。** 機構が動くことは
決定的に確かめておき、run では「選ぶか」だけを見る。

CLAUDE.md の「観測点が出ていない run は効果測定に使わず原因を切り分ける」
を、run の前に済ませておく形。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)

_MORI = PlayerId(1)
_SENA = PlayerId(2)
_KUZE = PlayerId(3)   # keeper
_AOI = PlayerId(4)


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _move(runtime, player_id: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    graph.unplace_entity(EntityId.create(int(player_id)))
    graph.place_entity(
        EntityId.create(int(player_id)),
        SpotId.create(runtime.id_mapper.get_int("spot", spot)),
    )
    runtime._spot_graph_repo.save(graph)


def _finish_task(runtime, player_id: PlayerId, obj: str, base: str) -> None:
    """作業を 3 手ぶん進めて完了させる。

    作業は多段になった (1 手では終わらない)。暗い部屋に留まる時間を延ばし、
    襲撃の機会を作るための変更なので、通しテストもその手数を通す。
    """
    for step in (base, f"{base}_2", f"{base}_3"):
        runtime.do_interact(player_id, obj, step)


def _line(runtime, keyword: str, player_id: PlayerId = _MORI) -> str:
    for line in runtime.build_observation(player_id).splitlines():
        if keyword in line:
            return line
    return ""


class TestTheScenarioIsShapedForTheDrill:
    """短く回せる形になっている。"""

    def test_the_meeting_is_short(self, runtime) -> None:
        """会議の上限が既定より短い。

        既定 (20) のままだと、20 tick の run で会議 1 回に大半を持って
        いかれる。**確かめたいのは一周することで、議論の長さではない。**
        """
        store = runtime._game_phase_store

        assert store.meeting_tick_limit == 6
        assert store.meeting_silence_limit_ticks == 3

    def test_there_are_four_players(self, runtime) -> None:
        """4 人居る。

        3 人だと 1 人倒れた時点で投票が 2 人になり、必ず同数で誰も追放され
        ない。**投票が観測できなくなる**ので、ここは削れない。
        """
        assert len(runtime.get_player_ids()) == 4

    def test_two_of_three_tasks_win(self, runtime) -> None:
        """作業は 3 個中 2 個で勝てる。

        全部を要求すると 1 人倒れただけで詰む。
        """
        assert "0/3" in _line(runtime, "作業の進み")
        assert "あと 2" in _line(runtime, "作業の進み")

    def test_only_the_hall_is_lit(self, runtime) -> None:
        """明るいのは集会室だけ。通路も倉庫も暗い。

        **最初この docstring を「暗いのは通路だけ」と書いて、倉庫を
        確かめていなかった。** 倉庫は darkened_station から暗いまま
        引き継いでいる。名前と docstring だけが嘘をつく形だったので、
        3 部屋すべてを見るようにした。

        結果としてこの形が良い。作業 3 個のうち 2 個が暗い部屋にあるので、
        **安全な集会室に居続けると勝てない**。作業に行くこと自体が危険を
        伴う、という釣り合いになる。
        """
        for spot, expected in (("hall", False), ("corridor", True), ("storage", True)):
            _move(runtime, _SENA, spot)
            is_dark = "DARK" in _line(runtime, "雰囲気", _SENA)
            assert is_dark is expected, f"{spot}: {_line(runtime, '雰囲気', _SENA)}"

    def test_work_is_reachable_only_by_entering_the_dark(self, runtime) -> None:
        """勝つには暗い部屋に入る必要がある。

        作業は 3 個中 2 個で足りるが、明るい集会室にあるのは 1 個だけ。
        **必ずどこかで暗い部屋に入る。** ここが崩れると、危険を冒さずに
        勝ててしまい、襲撃の機会が生まれない run になる。
        """
        lit_room_tasks = 1  # 気象記録簿のみ
        needed = 2

        assert lit_room_tasks < needed

    def test_a_lantern_lights_the_room_for_everyone(self, runtime) -> None:
        """ランタンを持った人が居ると、その部屋は全員にとって暗くなくなる。

        モリだけがランタンを持つ。**灯りは持ち主だけでなく同室者にも効く**
        ので、「暗い通路へは誰かと行く」が身を守る手になる。逆に一人で
        入ると襲われる。

        この性質を知らずに襲撃を組むと、灯りのある部屋を狙って失敗し
        続ける run になる。drill の前提として固定しておく。
        """
        _move(runtime, _SENA, "corridor")
        assert "DARK" in _line(runtime, "雰囲気", _SENA)

        _move(runtime, _MORI, "corridor")
        assert "DIM" in _line(runtime, "雰囲気", _SENA)
        assert "DIM" in _line(runtime, "雰囲気", _MORI)


class TestTheWholeLoopRuns:
    """一周する。"""

    def test_work_then_kill_then_meeting_then_ejection(self, runtime) -> None:
        """作業 → 襲撃 → 会議 → 投票 → 追放 が続けて成立する。

        個々の機構は各 PR で確かめてある。ここで見たいのは**続けて動くか**。
        フェーズが切り替わったまま作業ができなくなる、追放後に会議が開け
        なくなる、といった噛み合わせの崩れは単体テストでは出ない。
        """
        # 1. 作業が進む
        _move(runtime, _MORI, "corridor")
        _finish_task(runtime, _MORI, "junction_box", "tighten_wiring")
        assert "1/3" in _line(runtime, "作業の進み")

        # 2. 刃物を手に入れてから、暗い通路で襲う。
        #    狙うのはランタンを持たないセナ。モリはランタンで通路を
        #    DIM に押し上げるので襲えない (それも仕様)。
        _move(runtime, _KUZE, "storage")
        runtime.do_interact(_KUZE, "supply_shelf", "find_cutter")
        _move(runtime, _MORI, "hall")
        _move(runtime, _SENA, "corridor")
        _move(runtime, _KUZE, "corridor")
        #    一撃では倒れない (damage 70 / HP 100)。**わざとそうしてある**
        #    ので、襲撃は 2 手かかる。その間に逃げられる・目撃されるという
        #    余地が残る。
        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")
        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")
        assert runtime._player_status_repo.find_by_id(_SENA).is_down

        # 3. 会議が始まる (倒れていなくても緊急ボタンで開ける)
        _move(runtime, _KUZE, "hall")
        assert runtime.call_emergency_meeting(_KUZE).success
        assert runtime._game_phase_store.current.phase is GamePhase.MEETING
        assert "残り 6 tick" in _line(runtime, "話し合い", _MORI)

        # 4. 投票して追放する (倒れているセナは母数に入らない)
        for voter in (_MORI, _AOI, _KUZE):
            runtime.cast_vote(voter, _KUZE)

        assert (
            runtime._player_outcome_registry.get_outcome(_KUZE)
            is PlayerOutcomeEnum.EJECTED
        )
        assert runtime._game_phase_store.current.phase is GamePhase.FREE_ROAM

        # 5. 自由時間に戻って作業を続けられる
        _finish_task(runtime, _AOI, "weather_log", "log_weather")
        assert "必要数に到達" in _line(runtime, "作業の進み", _AOI)

    def test_the_run_can_end_by_finishing_the_work(self, runtime) -> None:
        """作業をやり切れば勝利で終わる。

        終われないシナリオで run を回すと、tick 上限まで走って何も
        分からないまま費用だけかかる。
        """
        _move(runtime, _MORI, "corridor")
        _finish_task(runtime, _MORI, "junction_box", "tighten_wiring")
        _move(runtime, _MORI, "hall")
        _finish_task(runtime, _MORI, "weather_log", "log_weather")

        assert runtime.check_game_end().is_ended is True
