"""`SpotGraphAggregate.emit_listen_carefully` のテスト (Phase 5 PR-2)。

検証対象:
- 自 spot の sound_intensity を減衰なしで観測する
- 隣接 spot の sound_intensity を `attenuate(1)` で観測する
- 減衰結果が SILENT の隣接 spot は event 発火しない
- 同 spot に複数 connection が向いていても 1 件に dedup される
- 自 spot が SILENT でも隣接 spot に音があれば隣接分は発火する
- 通行不可だが permeability が高い接続 (barrier 等) でも音は届く
- entity が graph 上に居なければ EntityNotInGraphException

NOTE: Phase 5 PR-3 で接続種別による減衰補正が入り、壁 INTACT (permeability
0.1) は実質的に音を遮断するモデルになった。「permeability に応じた hops」
の挙動は `test_spot_graph_sound_permeability_attenuation.py` で詳細にカバー
する。本ファイルは「自 spot + 隣接 dedup + 例外」の挙動を中心に検証する。
"""

from __future__ import annotations

import pytest

from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import (
    SpotGraphAggregate,
)
from ai_rpg_world.domain.world_graph.entity.spot_connection import SpotConnection
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.enum.lighting_enum import LightingEnum
from ai_rpg_world.domain.world_graph.enum.sound_intensity_enum import (
    SoundIntensityEnum,
)
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    SpotSoundHeardEvent,
)
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    EntityNotInGraphException,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.passage import Passage
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import (
    SpotAtmosphere,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId.create(1)
SPOT_B = SpotId.create(2)
SPOT_C = SpotId.create(3)


def _node(
    spot_id: SpotId, *,
    intensity: SoundIntensityEnum = SoundIntensityEnum.SILENT,
    ambient: str | None = None,
) -> SpotNode:
    return SpotNode(
        spot_id=spot_id, name=f"spot{spot_id.value}", description="",
        category=SpotCategoryEnum.OTHER, parent_id=None,
        atmosphere=SpotAtmosphere(
            lighting=LightingEnum.BRIGHT,
            sound_ambient=ambient,
            temperature=TemperatureEnum.NORMAL,
            smell=None,
            sound_intensity=intensity,
        ),
    )


def _conn(
    cid: int, from_id: SpotId, to_id: SpotId, *, traversable: bool = True,
) -> SpotConnection:
    # 通行不可な接続は wall(INTACT) で代表 (sound_permeability は本 PR では
    # 使わないので default で OK)。
    passage = Passage.open() if traversable else Passage.wall()
    return SpotConnection(
        connection_id=ConnectionId.create(cid),
        from_spot_id=from_id, to_spot_id=to_id,
        name=f"c{cid}", description="", travel_ticks=1,
        is_bidirectional=False, passage=passage,
    )


def _events(graph: SpotGraphAggregate) -> list[SpotSoundHeardEvent]:
    return [e for e in graph.get_events() if isinstance(e, SpotSoundHeardEvent)]


class TestEmitListenCarefullySelfSpot:
    """自 spot の音を減衰なしで観測する。"""

    def test_spot_moderate_event_trigger(self) -> None:
        """自 spotMODERATE の event が減衰なしで発火。"""
        g = SpotGraphAggregate.empty(GRAPH_ID)
        g.add_spot(_node(SPOT_A, intensity=SoundIntensityEnum.MODERATE, ambient="泉"))
        eid = EntityId.create(7)
        g.place_entity(eid, SPOT_A)
        g.clear_events()

        g.emit_listen_carefully(eid)

        events = _events(g)
        assert len(events) == 1
        ev = events[0]
        assert ev.spot_id == SPOT_A
        assert ev.source_spot_id == SPOT_A
        assert ev.intensity == "MODERATE"
        assert ev.ambient_description == "泉"

    def test_spot_silent_neighbor_does_not_trigger(self) -> None:
        """自 spot SILENT 隣接なし では 何も発火しない。"""
        g = SpotGraphAggregate.empty(GRAPH_ID)
        g.add_spot(_node(SPOT_A))  # SILENT
        eid = EntityId.create(7)
        g.place_entity(eid, SPOT_A)
        g.clear_events()

        g.emit_listen_carefully(eid)
        assert _events(g) == []


class TestEmitListenCarefullyAdjacent:
    """隣接 spot は attenuate(1) で観測する。"""

    def test_loud_neighbor_moderate_trigger(self) -> None:
        """LOUD な隣接は MODERATE に減衰して発火。"""
        g = SpotGraphAggregate.empty(GRAPH_ID)
        g.add_spot(_node(SPOT_A))  # 自 spot SILENT
        g.add_spot(_node(SPOT_B, intensity=SoundIntensityEnum.LOUD, ambient="戦闘音"))
        g.add_connection(_conn(10, SPOT_A, SPOT_B))
        eid = EntityId.create(7)
        g.place_entity(eid, SPOT_A)
        g.clear_events()

        g.emit_listen_carefully(eid)

        events = _events(g)
        assert len(events) == 1
        ev = events[0]
        assert ev.spot_id == SPOT_A  # listener は自 spot に居る
        assert ev.source_spot_id == SPOT_B  # 音源は隣接 spot
        assert ev.intensity == "MODERATE"  # LOUD - 1 = MODERATE
        assert ev.ambient_description == "戦闘音"

    def test_faint_neighbor_does_not_trigger(self) -> None:
        """FAINT な隣接は減衰しきって発火しない。"""
        g = SpotGraphAggregate.empty(GRAPH_ID)
        g.add_spot(_node(SPOT_A))
        g.add_spot(_node(SPOT_B, intensity=SoundIntensityEnum.FAINT, ambient="虫"))
        g.add_connection(_conn(10, SPOT_A, SPOT_B))
        eid = EntityId.create(7)
        g.place_entity(eid, SPOT_A)
        g.clear_events()

        g.emit_listen_carefully(eid)
        assert _events(g) == []  # FAINT - 1 = SILENT なので発火しない

    def test_traversable_permeability(
        self,
    ) -> None:
        """barrier ACTIVE (traversable=False, permeability=1.0) は通行不可
        だが音は通る、を表す。Phase 5 PR-3 で permeability ベースの伝搬に
        移行した後も `traversable` 単独では音を遮らないことを保証する。
        """
        from ai_rpg_world.domain.world_graph.enum.passage_kind import (
            BarrierStateEnum,
        )
        g = SpotGraphAggregate.empty(GRAPH_ID)
        g.add_spot(_node(SPOT_A))
        g.add_spot(_node(SPOT_B, intensity=SoundIntensityEnum.MODERATE))
        g.add_connection(SpotConnection(
            connection_id=ConnectionId.create(10),
            from_spot_id=SPOT_A, to_spot_id=SPOT_B,
            name="barrier", description="", travel_ticks=1,
            is_bidirectional=False,
            passage=Passage.barrier(BarrierStateEnum.ACTIVE),
        ))
        eid = EntityId.create(7)
        g.place_entity(eid, SPOT_A)
        g.clear_events()

        g.emit_listen_carefully(eid)

        events = _events(g)
        assert len(events) == 1
        assert events[0].source_spot_id == SPOT_B
        # permeability 1.0 → 1 hop → MODERATE - 1 = FAINT
        assert events[0].intensity == "FAINT"


class TestEmitListenCarefullyDedup:
    """複数 connection が同一隣接 spot を指していても 1 件にまとまる。"""

    def test_same_spot_multiple_connection_one_dedup(self) -> None:
        """同一 spot への 複数 connection は 1 件に dedup。"""
        g = SpotGraphAggregate.empty(GRAPH_ID)
        g.add_spot(_node(SPOT_A))
        g.add_spot(_node(SPOT_B, intensity=SoundIntensityEnum.LOUD))
        g.add_connection(_conn(10, SPOT_A, SPOT_B))
        g.add_connection(_conn(11, SPOT_A, SPOT_B))  # 同じ to_spot
        eid = EntityId.create(7)
        g.place_entity(eid, SPOT_A)
        g.clear_events()

        g.emit_listen_carefully(eid)

        events = _events(g)
        assert len(events) == 1
        assert events[0].source_spot_id == SPOT_B


class TestEmitListenCarefullyCombined:
    """自 spot と複数隣接 spot を組み合わせた典型ケース。"""

    def test_spot_moderate_neighbor_two_event_trigger(self) -> None:
        """自 spotMODERATE と隣接 2 件両方 event 発火。"""
        g = SpotGraphAggregate.empty(GRAPH_ID)
        g.add_spot(_node(SPOT_A, intensity=SoundIntensityEnum.MODERATE, ambient="A音"))
        g.add_spot(_node(SPOT_B, intensity=SoundIntensityEnum.LOUD, ambient="B音"))
        g.add_spot(_node(SPOT_C, intensity=SoundIntensityEnum.MODERATE, ambient="C音"))
        g.add_connection(_conn(10, SPOT_A, SPOT_B))
        g.add_connection(_conn(11, SPOT_A, SPOT_C))
        eid = EntityId.create(7)
        g.place_entity(eid, SPOT_A)
        g.clear_events()

        g.emit_listen_carefully(eid)

        events = _events(g)
        # A (自 spot MODERATE) + B (LOUD -> MODERATE) + C (MODERATE -> FAINT)
        assert len(events) == 3
        by_source = {e.source_spot_id: e for e in events}
        assert by_source[SPOT_A].intensity == "MODERATE"
        assert by_source[SPOT_A].spot_id == SPOT_A  # listener == source
        assert by_source[SPOT_B].intensity == "MODERATE"
        assert by_source[SPOT_B].spot_id == SPOT_A  # listener 位置は不変
        assert by_source[SPOT_C].intensity == "FAINT"


class TestEmitListenCarefullyErrors:
    """前提条件違反は EntityNotInGraphException。"""

    def test_entity_raises_exception(self) -> None:
        """未配置 entity では 例外。"""
        g = SpotGraphAggregate.empty(GRAPH_ID)
        g.add_spot(_node(SPOT_A))

        with pytest.raises(EntityNotInGraphException):
            g.emit_listen_carefully(EntityId.create(999))
