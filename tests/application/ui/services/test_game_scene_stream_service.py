"""Tests for GameSceneStreamService."""

from ai_rpg_world.application.ui.contracts.dtos import GameSceneDeltaEventDto
from ai_rpg_world.application.ui.services.game_scene_stream_service import (
    GameSceneStreamService,
)
from ai_rpg_world.infrastructure.ui.in_memory_game_scene_event_broker import (
    InMemoryGameSceneEventBroker,
)


def test_get_events_since_filters_by_scene_and_version():
    broker = InMemoryGameSceneEventBroker()
    broker.publish(
        GameSceneDeltaEventDto(
            event_id="1",
            event_type="actor_moved",
            scene_id="spot-1",
            spot_id=1,
            scene_version=1,
            emitted_at_ms=1,
            payload={},
        )
    )
    broker.publish(
        GameSceneDeltaEventDto(
            event_id="2",
            event_type="weather_changed",
            scene_id="spot-1",
            spot_id=1,
            scene_version=2,
            emitted_at_ms=2,
            payload={},
        )
    )
    broker.publish(
        GameSceneDeltaEventDto(
            event_id="3",
            event_type="actor_moved",
            scene_id="spot-2",
            spot_id=2,
            scene_version=1,
            emitted_at_ms=3,
            payload={},
        )
    )
    service = GameSceneStreamService(broker)

    events = service.get_events_since(scene_id="spot-1", last_seen_scene_version=1)

    assert [event.event_id for event in events] == ["2"]

