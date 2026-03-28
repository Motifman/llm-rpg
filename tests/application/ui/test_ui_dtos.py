"""Tests for UI DTO validation."""

import pytest

from ai_rpg_world.application.ui.contracts.dtos import (
    GameSceneDeltaEventDto,
    GameSceneSnapshotDto,
    SceneActorDto,
    SceneCameraDto,
    SceneMapDto,
    SimulationStateDto,
)


def _make_snapshot(**overrides) -> GameSceneSnapshotDto:
    params = {
        "scene_id": "spot-1",
        "spot_id": 1,
        "spot_name": "Town",
        "map": SceneMapDto(
            map_asset_key="town_map",
            tiled_map_path="maps/town.json",
            tile_width=32,
            tile_height=32,
            map_width_tiles=20,
            map_height_tiles=20,
            collision_layer_name="collision",
            tileset_keys=["terrain.tsx"],
        ),
        "camera": SceneCameraDto(
            mode="fixed",
            tracked_actor_id=None,
            viewport_width=1280,
            viewport_height=720,
        ),
        "simulation": SimulationStateDto(is_paused=False, speed_multiplier=1.0),
        "actors": [],
        "monsters": [],
        "gateways": [],
        "areas": [],
        "ui_logs": [],
        "scene_version": 0,
        "server_time_ms": 123,
    }
    params.update(overrides)
    return GameSceneSnapshotDto(**params)


def test_game_scene_snapshot_accepts_valid_payload():
    actor = SceneActorDto(
        actor_id=1,
        player_id=1,
        display_name="Hero",
        actor_kind="player",
        tile_x=3,
        tile_y=4,
        facing="down",
        sprite_key="player_default",
    )
    snapshot = _make_snapshot(actors=[actor])
    assert snapshot.actors[0].display_name == "Hero"
    assert snapshot.map.map_asset_key == "town_map"


def test_game_scene_snapshot_rejects_invalid_actor_list_item():
    with pytest.raises(TypeError, match="actors must contain only SceneActorDto"):
        _make_snapshot(actors=["invalid"])  # type: ignore[list-item]


def test_game_scene_delta_event_rejects_non_dict_payload():
    with pytest.raises(TypeError, match="payload must be dict"):
        GameSceneDeltaEventDto(
            event_id="evt-1",
            event_type="actor_moved",
            scene_id="spot-1",
            spot_id=1,
            scene_version=1,
            emitted_at_ms=1,
            payload=[],  # type: ignore[arg-type]
        )

