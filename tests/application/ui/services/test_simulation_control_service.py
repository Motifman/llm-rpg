"""Tests for SimulationControlService."""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.ui.contracts.dtos import (
    GameSceneSnapshotDto,
    SceneCameraDto,
    SceneMapDto,
    SimulationStateDto,
)
from ai_rpg_world.application.ui.exceptions import SimulationSpeedValidationException
from ai_rpg_world.application.ui.services.game_scene_projection import GameSceneProjection
from ai_rpg_world.application.ui.services.simulation_control_service import (
    SimulationControlService,
)
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
        scene_version=0,
        server_time_ms=0,
    )


def test_pause_updates_all_snapshots_and_publishes_events():
    projection = GameSceneProjection()
    projection.upsert_snapshot(_make_snapshot(1))
    projection.upsert_snapshot(_make_snapshot(2))
    broker = InMemoryGameSceneEventBroker()
    runtime_control = MagicMock()
    service = SimulationControlService(
        projection,
        broker,
        runtime_control=runtime_control,
    )

    service.pause()

    assert projection.get_snapshot(1).simulation.is_paused is True
    assert projection.get_snapshot(2).simulation.is_paused is True
    assert [event.event_type for event in broker.get_published_events()] == [
        "simulation_paused",
        "simulation_paused",
    ]
    runtime_control.pause.assert_called_once_with()


def test_set_speed_updates_projection_and_runtime_control():
    projection = GameSceneProjection()
    projection.upsert_snapshot(_make_snapshot(1))
    broker = InMemoryGameSceneEventBroker()
    runtime_control = MagicMock()
    service = SimulationControlService(
        projection,
        broker,
        runtime_control=runtime_control,
    )

    service.set_speed(speed_multiplier=2.5)

    assert projection.get_snapshot(1).simulation.speed_multiplier == 2.5
    assert broker.get_published_events()[0].event_type == "simulation_speed_changed"
    runtime_control.set_speed_multiplier.assert_called_once_with(2.5)


def test_set_speed_rejects_non_positive_value():
    projection = GameSceneProjection()
    projection.upsert_snapshot(_make_snapshot(1))
    broker = InMemoryGameSceneEventBroker()
    service = SimulationControlService(projection, broker)

    with pytest.raises(SimulationSpeedValidationException, match="greater than 0"):
        service.set_speed(speed_multiplier=0)

