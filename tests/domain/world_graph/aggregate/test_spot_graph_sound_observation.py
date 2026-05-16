"""spot 入場 / 移動時の `SpotSoundHeardEvent` 発火テスト (Phase 5)。

検証対象:
- sound_intensity=SILENT の spot に入っても event 発火しない
- sound_intensity > SILENT の spot に入ると event 発火
- move_entity で移動先 spot の音が観測される
- ambient_description が event に乗る
"""

from __future__ import annotations

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


def _events_of_type(graph: SpotGraphAggregate, evt_type) -> list:
    return [e for e in graph.get_events() if isinstance(e, evt_type)]


class TestPlaceEntitySilence:
    """SILENT な spot に入っても event 発火しない。"""

    def test_SILENT_spot_では_event_発火_なし(self) -> None:
        g = SpotGraphAggregate.empty(GRAPH_ID)
        g.add_spot(_node(SPOT_A))  # SILENT
        g.clear_events()

        g.place_entity(EntityId.create(7), SPOT_A)
        events = _events_of_type(g, SpotSoundHeardEvent)
        assert events == []


class TestPlaceEntityWithSound:
    """sound_intensity > SILENT の spot に入ると event 発火。"""

    def test_MODERATE_spot_で_event_発火_intensity_と_ambient_が_乗る(
        self,
    ) -> None:
        g = SpotGraphAggregate.empty(GRAPH_ID)
        g.add_spot(_node(
            SPOT_A,
            intensity=SoundIntensityEnum.MODERATE,
            ambient="川のせせらぎ",
        ))
        g.clear_events()

        entity_id = EntityId.create(7)
        g.place_entity(entity_id, SPOT_A)
        events = _events_of_type(g, SpotSoundHeardEvent)
        assert len(events) == 1
        ev = events[0]
        assert ev.entity_id == entity_id
        assert ev.spot_id == SPOT_A
        assert ev.source_spot_id == SPOT_A  # 自分が居る spot からの音
        assert ev.intensity == "MODERATE"
        assert ev.ambient_description == "川のせせらぎ"

    def test_LOUD_spot_で_intensity_LOUD(self) -> None:
        g = SpotGraphAggregate.empty(GRAPH_ID)
        g.add_spot(_node(SPOT_A, intensity=SoundIntensityEnum.LOUD))

        g.place_entity(EntityId.create(7), SPOT_A)
        events = _events_of_type(g, SpotSoundHeardEvent)
        assert len(events) == 1
        assert events[0].intensity == "LOUD"
        # ambient_description は None でも OK
        assert events[0].ambient_description is None


class TestMoveEntityWithSound:
    """move_entity で移動先 spot の音が観測される。"""

    def test_移動先_spot_の_sound_を_event_で_観測(self) -> None:
        g = SpotGraphAggregate.empty(GRAPH_ID)
        g.add_spot(_node(SPOT_A))  # 静か
        g.add_spot(_node(
            SPOT_B,
            intensity=SoundIntensityEnum.FAINT,
            ambient="風の音",
        ))
        g.add_connection(SpotConnection(
            connection_id=ConnectionId.create(10),
            from_spot_id=SPOT_A, to_spot_id=SPOT_B,
            name="path", description="", travel_ticks=1,
            is_bidirectional=False, passage=Passage.open(),
        ))
        entity_id = EntityId.create(7)
        g.place_entity(entity_id, SPOT_A)
        g.clear_events()  # 入場 event を捨てる (SILENT なので Sound event は無いが念のため)

        g.move_entity(
            entity_id=entity_id,
            connection_id=ConnectionId.create(10),
            owned_item_spec_ids=frozenset(),
            world_flags=frozenset(),
        )

        events = _events_of_type(g, SpotSoundHeardEvent)
        assert len(events) == 1
        assert events[0].entity_id == entity_id
        assert events[0].spot_id == SPOT_B
        assert events[0].intensity == "FAINT"
        assert events[0].ambient_description == "風の音"
