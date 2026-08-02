"""暗くて見えないことを明示し、殺した本人に死体発見を出さない。

## どちらも実 run 010 で出た

**暗い部屋でオブジェクトの節が丸ごと消えていた。** ハギは機関室で発電機を
見つけられず、こう推測して手番を溶かした。

    「照明が落ちてるから、もっと調べないと見つからないのか」

これは**このリポジトリが既に潰した形**。同席者とモンスターの節は #283 後続で
「居なければその旨を明示する」に直してある。オブジェクトだけ漏れていた。
しかもここでは **「何も無い」と「暗くて見えない」という別の事実が同じ沈黙に
潰れていた**。

**死体発見の観測が、殺した本人にだけ届いていた。** 加害者は現場に残るので
当然そうなる。run 010 では 3 人殺されて発見が 3 回出たが、3 回とも殺した
本人にしか届かなかった。文面としても「自分が作った死体を見つけた」は
成立していない。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_DRILL = (
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "station_drill.json"
)

_MORI, _SENA, _KUZE, _AOI, _HAGI = (PlayerId(i) for i in range(1, 6))


def _move(runtime, player_id: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    graph.unplace_entity(EntityId.create(int(player_id)))
    graph.place_entity(
        EntityId.create(int(player_id)),
        SpotId.create(runtime.id_mapper.get_int("spot", spot)),
    )
    runtime._spot_graph_repo.save(graph)


def _object_line(runtime, player_id: PlayerId) -> str:
    return next(
        (
            l for l in runtime.build_observation(player_id).splitlines()
            if l.startswith("オブジェクト")
        ),
        "",
    )


class TestDarkRoomsSaySo:
    """暗くて見えないことを、黙らずに書く。"""

    def test_a_dark_room_says_it_is_too_dark(self) -> None:
        """暗い部屋で「見えない」と出る。

        節ごと消すと、LLM は「節が無い = 何も無い」と推論するしかない。
        """
        runtime = create_world_runtime(_DRILL)
        _move(runtime, _HAGI, "machine_room")

        assert "暗くて何も見えない" in _object_line(runtime, _HAGI)

    def test_a_light_makes_the_objects_appear(self) -> None:
        """灯りがあれば物が見える。

        **「常に見えない」でもテストは通る**ので、見える側を一緒に見る。
        """
        runtime = create_world_runtime(_DRILL)
        _move(runtime, _HAGI, "machine_room")
        _move(runtime, _MORI, "machine_room")  # ランタン持ち

        assert "発電機" in runtime.build_observation(_HAGI)

    def test_an_empty_lit_room_says_it_is_empty(self) -> None:
        """明るくて何も無い部屋は、そう書く。

        「何も無い」と「見えない」は**別の事実**。同じ沈黙に潰さない。

        station_drill には「明るくて空の部屋」が無いので、分岐だけを直接
        見る。暗い側は上の 2 件が実際の世界で確かめている。
        """
        from unittest.mock import MagicMock

        from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (  # noqa: E501
            SpotGraphUiContextBuilder,
        )

        lines: list[str] = []
        snap = MagicMock(objects=(), atmosphere=MagicMock(lighting="BRIGHT"))
        SpotGraphUiContextBuilder()._build_object_section(
            snap, MagicMock(), MagicMock(), lines
        )

        assert lines == ["オブジェクト: (ここには何も無い)"]

    def test_a_room_with_no_atmosphere_is_not_called_dark(self) -> None:
        """明るさの宣言が無い世界を「暗い」と言わない。

        判定材料が無いのに暗いと書くと、灯りを探しに行かせることになる。
        """
        from unittest.mock import MagicMock

        from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (  # noqa: E501
            SpotGraphUiContextBuilder,
        )

        lines: list[str] = []
        SpotGraphUiContextBuilder()._build_object_section(
            MagicMock(objects=(), atmosphere=None), MagicMock(), MagicMock(), lines
        )

        assert "暗くて" not in lines[0]


class TestTheKillerIsNotToldWhatTheyDid:
    """殺した本人に、死体発見の観測が届かない。"""

    @pytest.fixture()
    def after_the_kill(self):
        runtime = create_world_runtime(_DRILL)
        _move(runtime, _KUZE, "storage")
        runtime.do_interact(_KUZE, "supply_shelf", "find_cutter")
        for player_id, spot in (
            (_SENA, "corridor"), (_KUZE, "corridor"), (_MORI, "hall")
        ):
            _move(runtime, player_id, spot)
        before = {
            int(p): len(runtime._obs_buffer.get_observations(p))
            for p in (_KUZE, _MORI)
        }
        runtime.do_interact_with_player(_KUZE, _SENA, "strike_down")
        runtime.advance_tick()
        return runtime, before

    def _findings(self, runtime, player_id, before) -> list:
        return [
            e.output.prose
            for e in runtime._obs_buffer.get_observations(player_id)[
                before[int(player_id)] :
            ]
            if "見つけた" in e.output.prose
        ]

    def test_the_killer_gets_nothing(self, after_the_kill) -> None:
        """加害者に「見つけた」が出ない。

        **run 010 ではこれが 3 回とも加害者にしか届いていなかった。**
        """
        runtime, before = after_the_kill
        runtime.build_observation(_KUZE)

        assert self._findings(runtime, _KUZE, before) == []

    def test_someone_arriving_later_still_finds_it(self, after_the_kill) -> None:
        """あとから来た人には今までどおり届く。

        **抑止しすぎると #926 が丸ごと死ぬ。** 通報の契機が消える。
        """
        runtime, before = after_the_kill
        _move(runtime, _MORI, "corridor")
        runtime.build_observation(_MORI)

        assert self._findings(runtime, _MORI, before)

    def test_a_death_without_a_killer_still_notifies(self) -> None:
        """加害者の居ない死では、抑止が働かない。

        餓死や事故で倒れた体は、**誰にとっても初めて見るもの**。
        """
        runtime = create_world_runtime(_DRILL)
        for player_id in (_SENA, _MORI):
            _move(runtime, player_id, "hall")
        status = runtime._player_status_repo.find_by_id(_SENA)
        before = len(runtime._obs_buffer.get_observations(_MORI))
        status.apply_damage(status.hp.value)  # killer 無し
        runtime._player_status_repo.save(status)
        runtime.advance_tick()
        runtime.build_observation(_MORI)

        assert [
            e.output.prose
            for e in runtime._obs_buffer.get_observations(_MORI)[before:]
            if "見つけた" in e.output.prose
        ]
