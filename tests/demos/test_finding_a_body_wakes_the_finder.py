"""倒れている人を見つけたら、見つけた本人が気づくことを保証する。

## 何が欠けていたか

死体は同席者行に出ていた。

    - "セナ" (死亡している) 〔手ぶら〕

**しかし観測イベントが発火していなかった。** 行は毎 tick そこにある
「見えている状態」で、観測は一度きりの「気づいた瞬間」。後者が無いと
``schedules_turn`` が立たないので、**死体の前を素通りする**。

実 run 008 でクルーが 2 人殺されたが、通報も会議も起きずに終わった。
別室で殺されたので誰も見ていない、というだけではない。**見つけたところで
起きない**構造だった。

## 同席者行と重複することについて

意図している。行は「いま見えているもの」、観測は「たったいま気づいたこと」。
片方だけにすると、

- 行だけ: 気づく契機が無い (いまの状態)
- 観測だけ: あとから来た人が「まだそこにあるのか」を確かめられない

## 一度きりの判定に既存の仕組みを使う

Encounter Memory (`EncounterKey(kind="body", ...)`) を使い、per-Being store を
増やさない。増やすと snapshot への追従が要る (CLAUDE.md #27)。monster の
初回観測と同じ形。

## 暗さは見ない

同席者行が暗所でも死体を出しているので、観測だけ隠すと**行と観測が食い違う**。
ランタンの意味を増やす案は魅力的だが、それは行のほうも隠す別の変更になる。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from tests.demos.station_drill_lighting_helpers import darken_spot

_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)

_MORI, _SENA, _KUZE, _AOI = (PlayerId(i) for i in (1, 2, 3, 4))

_FOUND = "見つけた"


def _move(runtime, player_id: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    graph.unplace_entity(EntityId.create(int(player_id)))
    graph.place_entity(
        EntityId.create(int(player_id)),
        SpotId.create(runtime.id_mapper.get_int("spot", spot)),
    )
    runtime._spot_graph_repo.save(graph)


def _new_findings(runtime, player_id: PlayerId, since: int) -> list:
    return [
        e
        for e in runtime._obs_buffer.get_observations(player_id)[since:]
        if _FOUND in e.output.prose
    ]


def _look(runtime, player_id: PlayerId) -> None:
    """その人の番が来たときと同じように現在状態を組む。

    発見は prompt 構築の中で起きる (monster の初回観測と同じ)。**観測を
    読む前にこれを呼ばないと、まだ発火していない。**
    """
    runtime.build_observation(player_id)


@pytest.fixture()
def world_with_a_body():
    """暗い通路にセナの死体があり、モリは離れた集会室に居る世界。"""
    runtime = create_world_runtime(_DRILL)
    _move(runtime, _KUZE, "storage")
    runtime.do_interact(_KUZE, "supply_shelf", "find_cutter")
    for player_id, spot in (
        (_SENA, "corridor"),
        (_KUZE, "corridor"),
        (_MORI, "hall"),
        (_AOI, "hall"),
    ):
        _move(runtime, player_id, spot)
    darken_spot(runtime)
    runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")
    runtime.advance_tick()
    return runtime


class TestTheFinderIsWokenUp:
    """見つけた本人に観測が届き、ターンが積まれる。"""

    def test_entering_the_room_produces_an_observation(self, world_with_a_body) -> None:
        """死体のある部屋に入ると観測が出る。"""
        runtime = world_with_a_body
        before = len(runtime._obs_buffer.get_observations(_MORI))

        _move(runtime, _MORI, "corridor")
        _look(runtime, _MORI)

        found = _new_findings(runtime, _MORI, before)
        assert found
        assert "セナ" in found[0].output.prose

    def test_it_schedules_a_turn(self, world_with_a_body) -> None:
        """観測がターンを積む。

        **これが今回の目的。** 立たないと、たまたま自分の番が回ってきて
        プロンプトを読むまで気づかない。通報が始まらない。
        """
        runtime = world_with_a_body
        before = len(runtime._obs_buffer.get_observations(_MORI))
        _move(runtime, _MORI, "corridor")
        _look(runtime, _MORI)

        assert _new_findings(runtime, _MORI, before)[0].output.schedules_turn is True

    def test_it_breaks_movement(self, world_with_a_body) -> None:
        """移動中でも足が止まる。

        死体を見つけて素通りするほうが不自然。
        """
        runtime = world_with_a_body
        before = len(runtime._obs_buffer.get_observations(_MORI))
        _move(runtime, _MORI, "corridor")
        _look(runtime, _MORI)

        assert _new_findings(runtime, _MORI, before)[0].output.breaks_movement is True


class TestItHappensOnlyOnce:
    """同じ体を二度「見つける」ことは無い。"""

    def test_looking_again_says_nothing(self, world_with_a_body) -> None:
        """同じ部屋に留まっても、二度目は出ない。

        毎 tick 出ると、そのぶん毎 tick 起こされて他に何もできなくなる。
        """
        runtime = world_with_a_body
        _move(runtime, _MORI, "corridor")
        _look(runtime, _MORI)

        before = len(runtime._obs_buffer.get_observations(_MORI))
        runtime.advance_tick()
        _look(runtime, _MORI)

        assert _new_findings(runtime, _MORI, before) == []

    def test_leaving_and_coming_back_says_nothing(self, world_with_a_body) -> None:
        """一度離れて戻っても出ない。

        記録は Encounter Memory なので、その場に居るかどうかではなく
        「一度見たか」で決まる。
        """
        runtime = world_with_a_body
        _move(runtime, _MORI, "corridor")
        _look(runtime, _MORI)

        before = len(runtime._obs_buffer.get_observations(_MORI))
        _move(runtime, _MORI, "hall")
        _look(runtime, _MORI)
        _move(runtime, _MORI, "corridor")
        _look(runtime, _MORI)

        assert _new_findings(runtime, _MORI, before) == []

    def test_a_different_finder_still_gets_it(self, world_with_a_body) -> None:
        """別の人は別に見つける。

        記録は人ごと。モリが見たからアオイが気づかない、では困る。
        """
        runtime = world_with_a_body
        _move(runtime, _MORI, "corridor")
        _look(runtime, _MORI)

        before = len(runtime._obs_buffer.get_observations(_AOI))
        _move(runtime, _AOI, "corridor")
        _look(runtime, _AOI)

        assert _new_findings(runtime, _AOI, before)


class TestWhoDoesNotGetIt:
    """届かないべき相手には届かない。"""

    def test_the_victim_does_not_find_their_own_body(self, world_with_a_body) -> None:
        """倒れた本人に、自分の体を見つけた観測は出ない。"""
        runtime = world_with_a_body

        _look(runtime, _SENA)

        assert [
            e
            for e in runtime._obs_buffer.get_observations(_SENA)
            if _FOUND in e.output.prose
        ] == []

    def test_players_elsewhere_learn_nothing(self, world_with_a_body) -> None:
        """別の部屋に居る人には届かない。

        **隠密殺人の前提。** ここが漏れると、死体を探しに行く意味が消える。
        """
        runtime = world_with_a_body
        before = len(runtime._obs_buffer.get_observations(_AOI))

        _look(runtime, _AOI)

        assert _new_findings(runtime, _AOI, before) == []


class TestTheObservationCarriesWhatMemoryNeeds:
    """記憶の索引に乗る形で残る。"""

    def test_it_records_who_and_where(self, world_with_a_body) -> None:
        """誰の体を、どこで見つけたかが structured に入る。

        episodic cue が読むのは `actor` と `spot_id_value`。この 2 つが
        無いと、**あとから「あの死体をどこで見たか」を思い出せない**。
        読まれない key を足しても飾りにしかならないので、読む側に合わせる。
        """
        runtime = world_with_a_body
        before = len(runtime._obs_buffer.get_observations(_MORI))
        _move(runtime, _MORI, "corridor")
        _look(runtime, _MORI)

        structured = _new_findings(runtime, _MORI, before)[0].output.structured

        assert structured["actor"] == "セナ"
        assert isinstance(structured.get("spot_id_value"), int)

    def test_it_does_not_name_any_tool(self, world_with_a_body) -> None:
        """文面に engine の識別子が出ない (#892)。

        「report_body で通報できる」と書きたくなるが、そのツールを落とした
        世界で嘘になる。
        """
        runtime = world_with_a_body
        before = len(runtime._obs_buffer.get_observations(_MORI))
        _move(runtime, _MORI, "corridor")
        _look(runtime, _MORI)

        prose = _new_findings(runtime, _MORI, before)[0].output.prose
        for name in ("report_body", "tend_to_player", "interact"):
            assert name not in prose
