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
from ai_rpg_world.application.world_graph.world_flag_state import (
    WorldFlagMutationContext,
    WorldFlagMutationSource,
)
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.game_phase import GamePhase
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from tests.demos.station_drill_lighting_helpers import darken_spot

_SCENARIO = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)

_MORI = PlayerId(1)
_SENA = PlayerId(2)
_KUZE = PlayerId(3)   # keeper
_AOI = PlayerId(4)
_HAGI = PlayerId(5)   # crew (機関担当)
_YURA = PlayerId(6)   # crew (担当なし)
_JIN = PlayerId(7)    # keeper
_SAKI = PlayerId(8)   # crew (記録担当)
_TASK_FLAGS = (
    "task_wind_instruments", "task_air_intake_flow",
    "task_observation_records", "task_inventory_ledger",
    "task_hygiene_supplies", "task_cold_storage",
    "task_cultivation_stock", "task_heating_fuel",
    "task_fuel_pump", "task_generator", "task_mainland_radio",
    "task_grow_light_wiring", "task_first_aid", "task_weather",
    "task_cable_labels", "task_exhaust_filter",
)
_SETUP_FLAG_CONTEXT = WorldFlagMutationContext(
    source=WorldFlagMutationSource.SCENARIO_EVENT,
    actor_player_id=None,
)


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


def _take_lantern(runtime, player_id: PlayerId) -> None:
    """暗い物資庫でも見える非常用ケースからランタンを取る。"""
    _move(runtime, player_id, "storage")
    runtime.build_observation(player_id)
    runtime.do_interact(player_id, "emergency_lantern_case", "take_lantern")


def _line(runtime, keyword: str, player_id: PlayerId = _MORI) -> str:
    for line in runtime.build_observation(player_id).splitlines():
        if keyword in line:
            return line
    return ""


class TestTheScenarioIsShapedForTheDrill:
    """短く回せる形になっている。"""

    def test_the_meeting_allows_ten_parallel_discussion_rounds(self, runtime) -> None:
        """8 人の並列会議は 10 tick 話せる一方、無発言 3 tick の打ち切りは維持する。"""
        store = runtime._game_phase_store

        assert store.meeting_tick_limit == 10
        assert store.meeting_silence_limit_ticks == 3

    def test_there_are_eight_players(self, runtime) -> None:
        """8 人居る (クルー 6 + インポスター 2)。"""
        assert len(runtime.get_player_ids()) == 8

    def test_twelve_of_the_sixteen_tasks_are_required(self, runtime) -> None:
        """作業は16件中12件必要で、六人が離れた二件を担当する長さにする。"""
        assert "0/16" in _line(runtime, "作業の進み")
        assert "あと 12" in _line(runtime, "作業の進み")

    def test_every_room_is_lit_before_a_blackout(self, runtime) -> None:
        """4室とも明るく始まり、担当作業を照明待ちにしない。"""
        for spot in ("hall", "corridor", "storage", "machine_room"):
            _move(runtime, _SENA, spot)
            assert "明るさ: 明るい" in _line(runtime, "雰囲気", _SENA), spot

    @pytest.mark.parametrize(
        ("player_id", "spot", "object_name", "action_name"),
        (
            (_MORI, "observatory", "風向風速計", "calibrate_wind_instruments"),
            (_SENA, "comms", "本土連絡無線機", "test_mainland_radio"),
            (_AOI, "medbay", "給食用衛生品棚", "count_catering_hygiene_supplies"),
            (_HAGI, "machine_room", "発電機", "check_generator"),
            (_YURA, "greenhouse", "栽培棚", "select_cultivation_stock"),
            (_SAKI, "observatory", "観測記録簿", "reconcile_observation_records"),
        ),
    )
    def test_each_duty_is_visible_without_a_lantern(
        self,
        runtime,
        player_id: PlayerId,
        spot: str,
        object_name: str,
        action_name: str,
    ) -> None:
        """4人の担当入口は、初期状態でランタン無しでも候補に出る。"""
        _move(runtime, player_id, spot)
        object_line = next(
            line
            for line in runtime.build_observation(player_id).splitlines()
            if line.startswith(f'  - "{object_name}"')
        )

        assert f'→ "{action_name}"' in object_line

    def test_a_lantern_lights_the_room_for_everyone(self, runtime) -> None:
        """ランタンを持った人が居ると、その部屋は全員にとって暗くなくなる。

        物資庫からランタンを取った人の灯りは、持ち主だけでなく同室者にも
        効く。だから「暗い通路へは誰かと行く」が身を守る手になる。逆に
        灯りを取らず一人で入ると襲われる。

        この性質を知らずに襲撃を組むと、灯りのある部屋を狙って失敗し
        続ける run になる。drill の前提として固定しておく。
        """
        darken_spot(runtime, "corridor")
        _move(runtime, _SENA, "corridor")
        assert "暗い" in _line(runtime, "雰囲気", _SENA)

        _take_lantern(runtime, _MORI)
        _move(runtime, _MORI, "corridor")
        assert "薄暗い" in _line(runtime, "雰囲気", _SENA)
        assert "薄暗い" in _line(runtime, "雰囲気", _MORI)


class TestTheWholeLoopRuns:
    """一周する。"""

    def test_work_then_kill_then_meeting_then_ejection(self, runtime) -> None:
        """作業 → 襲撃 → 会議 → 投票 → 追放 が続けて成立する。

        個々の機構は各 PR で確かめてある。ここで見たいのは**続けて動くか**。
        フェーズが切り替わったまま作業ができなくなる、追放後に会議が開け
        なくなる、といった噛み合わせの崩れは単体テストでは出ない。
        """
        # 1. 作業が進む (通信室の無線機はセナの担当)
        _move(runtime, _SENA, "comms")
        _finish_task(runtime, _SENA, "mainland_radio", "test_mainland_radio")
        assert "1/16" in _line(runtime, "作業の進み")

        # 2. 刃物を手に入れてから、暗い通路で襲う。
        #    狙うのはランタンを持たないセナ。モリはランタンで通路を
        #    DIM に押し上げるので襲えない (それも仕様)。
        _move(runtime, _KUZE, "storage")
        runtime.do_interact(_KUZE, "supply_shelf", "find_cutter")
        _move(runtime, _MORI, "hall")
        darken_spot(runtime, "corridor")
        _move(runtime, _KUZE, "corridor")
        _move(runtime, _SENA, "corridor")
        #    一撃で倒れる (damage 100 / HP 100)。本家に合わせてある。
        #    **再使用間隔があるので、続けてもう一人は襲えない。**
        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")
        assert runtime._player_status_repo.find_by_id(_SENA).is_down

        # 3. 会議が始まる (倒れていなくても緊急ボタンで開ける)
        _move(runtime, _KUZE, "hall")
        assert runtime.call_emergency_meeting(_KUZE).success
        assert runtime._game_phase_store.current.phase is GamePhase.MEETING
        assert "あと 50 分" in _line(runtime, "話し合い", _MORI)
        assert "あと 10 回ぶん" in _line(runtime, "話し合い", _MORI)

        # 4. 投票して追放する (倒れているセナは母数に入らない)
        #    **生きている全員が投票しないと締まらない。** ハギを足し忘れると
        #    集計が始まらず、「追放されなかった」と区別が付かない。
        for voter in (_MORI, _AOI, _HAGI, _YURA, _SAKI, _JIN, _KUZE):
            runtime.cast_vote(voter, _KUZE)

        assert (
            runtime._player_outcome_registry.get_outcome(_KUZE)
            is PlayerOutcomeEnum.EJECTED
        )
        assert runtime._game_phase_store.current.phase is GamePhase.FREE_ROAM

        # 5. 自由時間に戻って作業を続けられる。
        _finish_task(runtime, _MORI, "weather_log", "log_weather")
        _move(runtime, _SAKI, "storage")
        _finish_task(runtime, _SAKI, "inventory_ledger", "count_supplies")
        assert "3/16" in _line(runtime, "作業の進み", _SAKI)

    def test_the_run_can_end_by_finishing_the_work(self, runtime) -> None:
        """作業をやり切れば勝利で終わる。

        終われないシナリオで run を回すと、tick 上限まで走って何も
        分からないまま費用だけかかる。
        """
        for flag in _TASK_FLAGS[:12]:
            runtime._world_flag_state.add(flag, context=_SETUP_FLAG_CONTEXT)

        assert runtime.check_game_end().is_ended is True

    def test_eleven_tasks_do_not_win_but_the_twelfth_does(self, runtime) -> None:
        """16件の境界は12件で、11件では続き12件目で勝利する。"""
        for flag in _TASK_FLAGS[:11]:
            runtime._world_flag_state.add(flag, context=_SETUP_FLAG_CONTEXT)

        assert runtime.check_game_end().is_ended is False

        runtime._world_flag_state.add(_TASK_FLAGS[11], context=_SETUP_FLAG_CONTEXT)

        assert runtime.check_game_end().is_ended is True

    def test_any_crew_member_can_finish_a_common_task(self, runtime) -> None:
        """気象担当のモリも、担当の無い気象記録を3段進められる。"""
        _move(runtime, _MORI, "hall")

        _finish_task(runtime, _MORI, "weather_log", "log_weather")

        assert "task_weather" in runtime._world_flag_state.as_frozen_set()

    @pytest.mark.parametrize("player_id", (_MORI, _SENA, _AOI, _HAGI, _YURA, _SAKI))
    @pytest.mark.parametrize(
        ("spot", "object_id", "action_name"),
        (
            ("hall", "weather_log", "log_weather"),
            ("hall", "first_aid_cabinet", "inspect_first_aid"),
            ("corridor", "cable_label_chart", "verify_cable_labels"),
            ("machine_room", "exhaust_filter", "clean_exhaust_filter"),
        ),
    )
    def test_every_crew_member_can_start_each_unassigned_room_task(
        self, runtime, player_id, spot, object_id, action_name
    ) -> None:
        """共通4件は、6人のクルー全員が公開入口を通れる。"""
        _move(runtime, player_id, spot)

        runtime.do_interact(player_id, object_id, action_name)

    @pytest.mark.parametrize(
        ("owner", "outsider", "spot", "object_id", "action_name"),
        (
            (_SENA, _MORI, "greenhouse", "grow_lights", "inspect_grow_light_wiring"),
            (_AOI, _SENA, "medbay", "medical_supply_shelf", "count_catering_hygiene_supplies"),
            (_HAGI, _MORI, "machine_room", "generator", "check_generator"),
            (_MORI, _HAGI, "observatory", "weather_instruments", "calibrate_wind_instruments"),
            (_YURA, _SENA, "greenhouse", "cultivation_rack", "select_cultivation_stock"),
            (_SAKI, _MORI, "observatory", "observation_records", "reconcile_observation_records"),
        ),
    )
    def test_only_the_assignee_can_start_each_assigned_task(
        self, runtime, owner, outsider, spot, object_id, action_name
    ) -> None:
        """新しい担当者は入口を通れ、同室の担当外クルーは直接呼んでも拒否される。"""
        _move(runtime, outsider, spot)
        with pytest.raises(InteractionNotAllowedException):
            runtime.do_interact(outsider, object_id, action_name)

        _move(runtime, owner, spot)
        runtime.do_interact(owner, object_id, action_name)
