"""Tests for ManualActorControlService."""

from unittest.mock import MagicMock

import pytest

from ai_rpg_world.application.ui.contracts.commands import MoveManualActorCommand
from ai_rpg_world.application.ui.contracts.dtos import (
    GameSceneSnapshotDto,
    SceneActorDto,
    SceneCameraDto,
    SceneMapDto,
    SimulationStateDto,
)
from ai_rpg_world.application.ui.exceptions import ManualControlForbiddenException
from ai_rpg_world.application.ui.services.game_scene_projection import GameSceneProjection
from ai_rpg_world.application.ui.services.manual_actor_control_service import (
    ManualActorControlService,
)
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum


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
        actors=[
            SceneActorDto(
                actor_id=1,
                player_id=1,
                display_name="Hero",
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


def test_move_delegates_to_movement_port_and_marks_actor_manual():
    movement_port = MagicMock()
    movement_port.move_tile.return_value = {"ok": True}
    projection = GameSceneProjection()
    projection.upsert_snapshot(_make_snapshot())
    service = ManualActorControlService(
        movement_port,
        projection,
        manual_player_ids=[1],
    )

    result = service.move(
        MoveManualActorCommand(player_id=1, direction=DirectionEnum.EAST)
    )

    snapshot = projection.get_snapshot(1)
    assert result == {"ok": True}
    assert snapshot.actors[0].is_manual_controlled is True
    assert snapshot.actors[0].is_llm_controlled is False
    move_command = movement_port.move_tile.call_args.args[0]
    assert move_command.player_id == 1
    assert move_command.direction is DirectionEnum.EAST


def test_move_rejects_non_manual_actor():
    movement_port = MagicMock()
    projection = GameSceneProjection()
    projection.upsert_snapshot(_make_snapshot())
    service = ManualActorControlService(
        movement_port,
        projection,
        manual_player_ids=[1],
    )

    with pytest.raises(ManualControlForbiddenException, match="player_id=2"):
        service.move(
            MoveManualActorCommand(player_id=2, direction=DirectionEnum.EAST)
        )

