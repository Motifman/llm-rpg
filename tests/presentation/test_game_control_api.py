"""Tests for GameControlApi."""

from unittest.mock import MagicMock

from ai_rpg_world.application.ui.contracts.commands import (
    InteractSceneObjectCommand,
    MoveManualActorCommand,
    PauseSimulationCommand,
    ResumeSimulationCommand,
    SetSimulationSpeedCommand,
)
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
from ai_rpg_world.presentation.game_control_api import GameControlApi


def test_game_control_api_delegates_to_underlying_services():
    simulation_control = MagicMock()
    manual_control = MagicMock()
    interaction_control = MagicMock()
    manual_control.move.return_value = {"ok": True}
    interaction_control.interact.return_value = {"opened": True}
    api = GameControlApi(simulation_control, manual_control, interaction_control)

    api.pause(PauseSimulationCommand())
    api.resume(ResumeSimulationCommand())
    api.set_speed(SetSimulationSpeedCommand(speed_multiplier=1.5))
    result = api.move_manual_actor(
        MoveManualActorCommand(player_id=1, direction=DirectionEnum.NORTH)
    )
    interaction_result = api.interact_scene_object(
        InteractSceneObjectCommand(player_id=1, target_object_id=2001)
    )

    simulation_control.pause.assert_called_once_with()
    simulation_control.resume.assert_called_once_with()
    simulation_control.set_speed.assert_called_once_with(speed_multiplier=1.5)
    manual_control.move.assert_called_once()
    interaction_control.interact.assert_called_once()
    assert result == {"ok": True}
    assert interaction_result == {"opened": True}
