"""Tests for the framework-agnostic GameSceneApi facade."""

from ai_rpg_world.application.ui.contracts.dtos import (
    GameSceneDeltaEventDto,
    GameSceneSnapshotDto,
    SceneCameraDto,
    SceneMapDto,
    SimulationStateDto,
)
from ai_rpg_world.application.ui.services.game_scene_projection import GameSceneProjection
from ai_rpg_world.application.ui.services.game_scene_snapshot_service import (
    GameSceneSnapshotService,
)
from ai_rpg_world.application.ui.services.game_scene_stream_service import (
    GameSceneStreamService,
)
from ai_rpg_world.infrastructure.ui.in_memory_game_scene_event_broker import (
    InMemoryGameSceneEventBroker,
)
from ai_rpg_world.presentation.game_scene_api import GameSceneApi


def _make_snapshot() -> GameSceneSnapshotDto:
    return GameSceneSnapshotDto(
        scene_id="spot-1",
        spot_id=1,
        spot_name="Town",
        map=SceneMapDto(
            map_asset_key="town_map",
            tiled_map_path="maps/town.json",
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


def test_game_scene_api_delegates_snapshot_and_stream_access():
    projection = GameSceneProjection()
    projection.upsert_snapshot(_make_snapshot())
    snapshot_service = GameSceneSnapshotService(projection)
    broker = InMemoryGameSceneEventBroker()
    broker.publish(
        GameSceneDeltaEventDto(
            event_id="evt-1",
            event_type="actor_moved",
            scene_id="spot-1",
            spot_id=1,
            scene_version=1,
            emitted_at_ms=1,
            payload={"actor_id": 1},
        )
    )
    stream_service = GameSceneStreamService(broker)
    api = GameSceneApi(snapshot_service, stream_service)

    snapshot = api.get_scene_snapshot(1)
    events = api.get_scene_events(scene_id="spot-1", last_seen_scene_version=0)
    overview = api.get_world_overview()

    assert snapshot.spot_name == "Town"
    assert [event.event_id for event in events] == ["evt-1"]
    assert overview[0].scene_id == "spot-1"

