"""接続種別による音減衰補正 (Phase 5 PR-3) のテスト。

`emit_listen_carefully` が `Passage.sound_permeability` を
`sound_permeability_to_hops` で量子化して `SoundIntensityEnum.attenuate`
に渡す挙動を検証する。

検証する主要シナリオ:
- 開口部 / 開いた扉 / 壊れた壁 (permeability 1.0) → 1 hop 減衰 (PR-2 既定)
- 閉じた扉 / 鍵付き扉 / ヒビ壁 (permeability 0.4-0.6) → 2 hops 減衰
- 通常の壁 (permeability 0.1) → 3 hops 減衰 (実質遮音)
- 同一隣接 spot に複数 connection があるとき: 最も透過率が高いものを採用
- 自 spot は permeability に依存せず常に減衰なし

`sound_permeability_to_hops` 単体の境界値テストも併せて。
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
from ai_rpg_world.domain.world_graph.enum.passage_kind import (
    DoorStateEnum,
    WallStateEnum,
)
from ai_rpg_world.domain.world_graph.enum.sound_intensity_enum import (
    SoundIntensityEnum,
)
from ai_rpg_world.domain.world_graph.enum.temperature_enum import TemperatureEnum
from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
    SpotSoundHeardEvent,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.passage import (
    Passage,
    sound_permeability_to_hops,
)
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import (
    SpotAtmosphere,
)
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


GRAPH_ID = SpotGraphId.create(1)
SPOT_A = SpotId.create(1)
SPOT_B = SpotId.create(2)


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


def _build_AB(
    *,
    intensity_B: SoundIntensityEnum,
    passage: Passage,
) -> tuple[SpotGraphAggregate, EntityId]:
    """A (SILENT) ←→ B (intensity_B) で接続だけ差し替えるヘルパー。"""
    g = SpotGraphAggregate.empty(GRAPH_ID)
    g.add_spot(_node(SPOT_A))
    g.add_spot(_node(SPOT_B, intensity=intensity_B, ambient="B音"))
    g.add_connection(SpotConnection(
        connection_id=ConnectionId.create(10),
        from_spot_id=SPOT_A, to_spot_id=SPOT_B,
        name="c", description="", travel_ticks=1,
        is_bidirectional=False, passage=passage,
    ))
    eid = EntityId.create(7)
    g.place_entity(eid, SPOT_A)
    g.clear_events()
    return g, eid


def _events(g: SpotGraphAggregate) -> list[SpotSoundHeardEvent]:
    return [e for e in g.get_events() if isinstance(e, SpotSoundHeardEvent)]


class TestSoundPermeabilityToHops:
    """量子化関数の境界値挙動。"""

    @pytest.mark.parametrize("permeability,expected_hops", [
        (1.0, 1),
        (0.7, 1),  # 境界
        (0.69, 2),
        (0.6, 2),  # DOOR.CLOSED
        (0.5, 2),  # DOOR.LOCKED
        (0.4, 2),  # 境界 / WALL.CRACKED
        (0.39, 3),
        (0.1, 3),  # 境界 / WALL.INTACT
        (0.09, 4),
        (0.0, 4),
    ])
    def test_境界値_で_期待_hops_を_返す(
        self, permeability: float, expected_hops: int,
    ) -> None:
        assert sound_permeability_to_hops(permeability) == expected_hops


class TestOpenPassage1Hop:
    """開口部 / 開いた扉 / 壊れた壁 (permeability 1.0) は 1 hop 減衰。"""

    def test_OPEN_LOUD_は_MODERATE_に_減衰(self) -> None:
        g, eid = _build_AB(
            intensity_B=SoundIntensityEnum.LOUD,
            passage=Passage.open(),
        )
        g.emit_listen_carefully(eid)
        events = _events(g)
        assert len(events) == 1
        assert events[0].intensity == "MODERATE"

    def test_WALL_BROKEN_LOUD_も_MODERATE_に_減衰(self) -> None:
        g, eid = _build_AB(
            intensity_B=SoundIntensityEnum.LOUD,
            passage=Passage.wall(WallStateEnum.BROKEN),
        )
        g.emit_listen_carefully(eid)
        events = _events(g)
        assert len(events) == 1
        assert events[0].intensity == "MODERATE"

    def test_DOOR_OPEN_MODERATE_は_FAINT_に_減衰(self) -> None:
        g, eid = _build_AB(
            intensity_B=SoundIntensityEnum.MODERATE,
            passage=Passage.door(DoorStateEnum.OPEN),
        )
        g.emit_listen_carefully(eid)
        events = _events(g)
        assert len(events) == 1
        assert events[0].intensity == "FAINT"


class TestClosedDoorAndCrackedWall2Hops:
    """閉じた扉 / 鍵付き扉 / ヒビ壁 (permeability 0.4-0.6) は 2 hops 減衰。"""

    def test_DOOR_CLOSED_LOUD_は_FAINT_に_減衰(self) -> None:
        g, eid = _build_AB(
            intensity_B=SoundIntensityEnum.LOUD,
            passage=Passage.door(DoorStateEnum.CLOSED),
        )
        g.emit_listen_carefully(eid)
        events = _events(g)
        assert len(events) == 1
        assert events[0].intensity == "FAINT"  # LOUD(3) - 2 = FAINT(1)

    def test_DOOR_CLOSED_MODERATE_は_SILENT_で_発火しない(self) -> None:
        g, eid = _build_AB(
            intensity_B=SoundIntensityEnum.MODERATE,
            passage=Passage.door(DoorStateEnum.CLOSED),
        )
        g.emit_listen_carefully(eid)
        assert _events(g) == []  # MODERATE(2) - 2 = SILENT

    def test_WALL_CRACKED_LOUD_は_FAINT_に_減衰(self) -> None:
        g, eid = _build_AB(
            intensity_B=SoundIntensityEnum.LOUD,
            passage=Passage.wall(WallStateEnum.CRACKED),
        )
        g.emit_listen_carefully(eid)
        events = _events(g)
        assert len(events) == 1
        assert events[0].intensity == "FAINT"


class TestIntactWall3Hops:
    """通常の壁 (permeability 0.1) は LOUD ですら遮断する。"""

    def test_WALL_INTACT_LOUD_は_SILENT_で_発火しない(self) -> None:
        g, eid = _build_AB(
            intensity_B=SoundIntensityEnum.LOUD,
            passage=Passage.wall(WallStateEnum.INTACT),
        )
        g.emit_listen_carefully(eid)
        # permeability 0.1 → 3 hops → LOUD(3) - 3 = SILENT
        assert _events(g) == []


class TestMultiConnectionPicksBestPath:
    """同一隣接 spot に複数 connection があるとき、最も透過率が高いものを採用。"""

    def test_壁_と_開いた扉_が_並ぶと_扉_側の_1_hop_減衰が採用される(
        self,
    ) -> None:
        """壁 INTACT (3 hops) と DOOR OPEN (1 hop) の両方が B を指している
        場合、音は扉を通って届くべき (= 1 hop で減衰)。
        """
        g = SpotGraphAggregate.empty(GRAPH_ID)
        g.add_spot(_node(SPOT_A))
        g.add_spot(_node(SPOT_B, intensity=SoundIntensityEnum.MODERATE, ambient="泉"))
        g.add_connection(SpotConnection(
            connection_id=ConnectionId.create(10),
            from_spot_id=SPOT_A, to_spot_id=SPOT_B,
            name="wall", description="", travel_ticks=1,
            is_bidirectional=False,
            passage=Passage.wall(WallStateEnum.INTACT),  # 3 hops
        ))
        g.add_connection(SpotConnection(
            connection_id=ConnectionId.create(11),
            from_spot_id=SPOT_A, to_spot_id=SPOT_B,
            name="door", description="", travel_ticks=1,
            is_bidirectional=False,
            passage=Passage.door(DoorStateEnum.OPEN),  # 1 hop
        ))
        eid = EntityId.create(7)
        g.place_entity(eid, SPOT_A)
        g.clear_events()

        g.emit_listen_carefully(eid)

        events = _events(g)
        assert len(events) == 1  # B への観測は 1 件に集約
        # 扉経由 (1 hop) で MODERATE(2) - 1 = FAINT(1)
        assert events[0].intensity == "FAINT"


class TestSelfSpotIgnoresPermeability:
    """自 spot の音は permeability の影響を受けず、常に減衰なし。"""

    def test_壁に囲まれた自_spot_でも_自分の音は減衰なし(self) -> None:
        g = SpotGraphAggregate.empty(GRAPH_ID)
        g.add_spot(_node(SPOT_A, intensity=SoundIntensityEnum.FAINT, ambient="心音"))
        g.add_spot(_node(SPOT_B))
        # 隣接が壁でも自 spot の sound には影響しない
        g.add_connection(SpotConnection(
            connection_id=ConnectionId.create(10),
            from_spot_id=SPOT_A, to_spot_id=SPOT_B,
            name="wall", description="", travel_ticks=1,
            is_bidirectional=False,
            passage=Passage.wall(WallStateEnum.INTACT),
        ))
        eid = EntityId.create(7)
        g.place_entity(eid, SPOT_A)
        g.clear_events()

        g.emit_listen_carefully(eid)

        events = _events(g)
        assert len(events) == 1
        assert events[0].source_spot_id == SPOT_A
        assert events[0].intensity == "FAINT"
