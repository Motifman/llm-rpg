"""Tests for UiEventHandler."""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.common.exceptions import SystemErrorException
from ai_rpg_world.application.ui.contracts.dtos import (
    GameSceneSnapshotDto,
    SceneActorDto,
    SceneCameraDto,
    SceneMapDto,
    SimulationStateDto,
)
from ai_rpg_world.application.ui.handlers.ui_event_handler import UiEventHandler
from ai_rpg_world.application.ui.services.game_scene_projection import GameSceneProjection
from ai_rpg_world.domain.player.event.status_events import PlayerLocationChangedEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.event.map_events import GatewayTriggeredEvent, SpotWeatherChangedEvent
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.ui.in_memory_game_scene_event_broker import (
    InMemoryGameSceneEventBroker,
)


def _make_snapshot(spot_id: int) -> GameSceneSnapshotDto:
    return GameSceneSnapshotDto(
        scene_id=f"spot-{spot_id}",
        spot_id=spot_id,
        spot_name=f"Spot {spot_id}",
        map=SceneMapDto(
            map_asset_key=f"spot_{spot_id}",
            tiled_map_path=f"maps/{spot_id}.json",
            tile_width=32,
            tile_height=32,
            map_width_tiles=10,
            map_height_tiles=10,
            collision_layer_name="collision",
            tileset_keys=["terrain.tsx"],
        ),
        camera=SceneCameraDto(
            mode="fixed",
            tracked_actor_id=None,
            viewport_width=640,
            viewport_height=480,
        ),
        simulation=SimulationStateDto(is_paused=False, speed_multiplier=1.0),
        actors=[
            SceneActorDto(
                actor_id=1,
                player_id=1,
                display_name="Player 1",
                actor_kind="player",
                tile_x=1,
                tile_y=1,
                facing="down",
                sprite_key="player_default",
            )
        ],
        scene_version=0,
        server_time_ms=0,
    )


def test_handle_player_location_changed_publishes_actor_moved():
    projection = GameSceneProjection()
    projection.upsert_snapshot(_make_snapshot(1))
    broker = InMemoryGameSceneEventBroker()
    handler = UiEventHandler(projection, broker)

    event = PlayerLocationChangedEvent.create(
        aggregate_id=PlayerId(1),
        aggregate_type="PlayerStatusAggregate",
        old_spot_id=SpotId(1),
        old_coordinate=Coordinate(1, 1, 0),
        new_spot_id=SpotId(1),
        new_coordinate=Coordinate(2, 1, 0),
    )
    handler.handle(event)

    published = broker.get_published_events()
    assert len(published) == 1
    assert published[0].event_type == "actor_moved"
    assert published[0].payload["to_tile_x"] == 2


def test_handle_gateway_triggered_publishes_scene_changed():
    projection = GameSceneProjection()
    projection.upsert_snapshot(_make_snapshot(1))
    projection.upsert_snapshot(_make_snapshot(2))
    broker = InMemoryGameSceneEventBroker()
    handler = UiEventHandler(projection, broker)

    event = GatewayTriggeredEvent.create(
        aggregate_id=GatewayId(10),
        aggregate_type="PhysicalMapAggregate",
        gateway_id=GatewayId(10),
        spot_id=SpotId(1),
        object_id=WorldObjectId(1),
        target_spot_id=SpotId(2),
        landing_coordinate=Coordinate(3, 4, 0),
        player_id_value=1,
    )
    handler.handle(event)

    published = broker.get_published_events()
    assert [item.event_type for item in published] == ["actor_removed", "scene_changed"]
    assert published[0].payload["target_spot_id"] == 2
    assert published[1].payload["to_spot_id"] == 2


def test_handle_weather_changed_publishes_overlay_event():
    projection = GameSceneProjection()
    projection.upsert_snapshot(_make_snapshot(1))
    broker = InMemoryGameSceneEventBroker()
    handler = UiEventHandler(projection, broker)

    event = SpotWeatherChangedEvent.create(
        aggregate_id=SpotId(1),
        aggregate_type="WeatherZone",
        spot_id=SpotId(1),
        old_weather_state=WeatherState.clear(),
        new_weather_state=WeatherState(WeatherTypeEnum.RAIN, 0.7),
    )
    handler.handle(event)

    published = broker.get_published_events()
    assert published[0].event_type == "weather_changed"
    assert published[0].payload["weather_overlay_key"] == "rain_light"


def test_handle_wraps_unexpected_errors():
    projection = MagicMock()
    broker = InMemoryGameSceneEventBroker()
    handler = UiEventHandler(projection, broker)
    projection.apply_actor_moved.side_effect = RuntimeError("boom")

    event = PlayerLocationChangedEvent.create(
        aggregate_id=PlayerId(1),
        aggregate_type="PlayerStatusAggregate",
        old_spot_id=SpotId(1),
        old_coordinate=Coordinate(1, 1, 0),
        new_spot_id=SpotId(1),
        new_coordinate=Coordinate(2, 1, 0),
    )
    with pytest.raises(SystemErrorException, match="UI event handling failed"):
        handler.handle(event)
