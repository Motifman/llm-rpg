"""Tests for GameSceneProjection."""

import pytest

from ai_rpg_world.application.ui.contracts.dtos import (
    GameSceneSnapshotDto,
    SceneActorDto,
    SceneCameraDto,
    SceneMapDto,
    SimulationStateDto,
)
from ai_rpg_world.application.ui.exceptions import GameSceneNotFoundException
from ai_rpg_world.application.ui.services.game_scene_projection import GameSceneProjection


def _make_snapshot(spot_id: int, actor_id: int | None = None) -> GameSceneSnapshotDto:
    actors = []
    if actor_id is not None:
        actors.append(
            SceneActorDto(
                actor_id=actor_id,
                player_id=actor_id,
                display_name=f"Player {actor_id}",
                actor_kind="player",
                tile_x=1,
                tile_y=1,
                facing="down",
                sprite_key="player_default",
            )
        )
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
        actors=actors,
        scene_version=0,
        server_time_ms=0,
    )


def test_apply_actor_moved_updates_existing_actor_and_returns_delta():
    projection = GameSceneProjection()
    projection.upsert_snapshot(_make_snapshot(1, actor_id=5))

    delta = projection.apply_actor_moved(
        spot_id=1,
        actor_id=5,
        to_tile_x=2,
        to_tile_y=3,
        facing="right",
        actor_kind="player",
        display_name="Player 5",
        sprite_key="player_default",
    )

    snapshot = projection.get_snapshot(1)
    assert snapshot.actors[0].tile_x == 2
    assert snapshot.actors[0].tile_y == 3
    assert delta.event_type == "actor_moved"
    assert delta.payload["from_tile_x"] == 1
    assert delta.payload["to_tile_x"] == 2


def test_apply_scene_changed_moves_actor_between_scenes():
    projection = GameSceneProjection()
    projection.upsert_snapshot(_make_snapshot(1, actor_id=5))
    projection.upsert_snapshot(_make_snapshot(2))

    source_delta, target_delta = projection.apply_scene_changed(
        actor_id=5,
        from_spot_id=1,
        to_spot_id=2,
        landing_tile_x=4,
        landing_tile_y=6,
        auto_follow_switched=True,
    )

    source = projection.get_snapshot(1)
    target = projection.get_snapshot(2)
    assert source.actors == []
    assert target.actors[0].actor_id == 5
    assert target.actors[0].tile_x == 4
    assert source_delta.event_type == "actor_removed"
    assert source_delta.payload["target_spot_id"] == 2
    assert target_delta.event_type == "scene_changed"
    assert target_delta.payload["to_spot_id"] == 2
    assert target_delta.payload["display_name"] == "Player 5"


def test_get_snapshot_raises_when_scene_missing():
    projection = GameSceneProjection()
    with pytest.raises(GameSceneNotFoundException, match="spot_id=99"):
        projection.get_snapshot(99)


def test_advance_simulation_tick_updates_tick_and_clears_expired_busy_actor():
    projection = GameSceneProjection()
    projection.upsert_snapshot(_make_snapshot(1, actor_id=5))
    projection.apply_actor_moved(
        spot_id=1,
        actor_id=5,
        to_tile_x=2,
        to_tile_y=3,
        facing="right",
        actor_kind="player",
        display_name="Player 5",
        sprite_key="player_default",
        busy_until_tick=12,
    )

    delta = projection.advance_simulation_tick(
        spot_id=1,
        current_tick=12,
        server_time_ms=999,
    )

    snapshot = projection.get_snapshot(1)
    assert snapshot.simulation.current_tick == 12
    assert snapshot.server_time_ms == 999
    assert snapshot.actors[0].state == "idle"
    assert snapshot.actors[0].busy_until_tick is None
    assert delta.event_type == "tick_advanced"
