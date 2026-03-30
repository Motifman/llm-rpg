"""Framework-agnostic facade for simulation and manual control actions."""

from __future__ import annotations

from ai_rpg_world.application.ui.contracts.commands import (
    InteractSceneObjectCommand,
    MoveManualActorCommand,
    PauseSimulationCommand,
    ResumeSimulationCommand,
    SetSimulationSpeedCommand,
)
from ai_rpg_world.application.ui.services.manual_actor_control_service import (
    ManualActorControlService,
)
from ai_rpg_world.application.ui.services.manual_object_interaction_service import (
    ManualObjectInteractionService,
)
from ai_rpg_world.application.ui.services.simulation_control_service import (
    SimulationControlService,
)


class GameControlApi:
    def __init__(
        self,
        simulation_control_service: SimulationControlService,
        manual_actor_control_service: ManualActorControlService,
        manual_object_interaction_service: ManualObjectInteractionService,
    ) -> None:
        self._simulation_control_service = simulation_control_service
        self._manual_actor_control_service = manual_actor_control_service
        self._manual_object_interaction_service = manual_object_interaction_service

    def pause(self, command: PauseSimulationCommand) -> None:
        self._simulation_control_service.pause()

    def resume(self, command: ResumeSimulationCommand) -> None:
        self._simulation_control_service.resume()

    def set_speed(self, command: SetSimulationSpeedCommand) -> None:
        self._simulation_control_service.set_speed(
            speed_multiplier=float(command.speed_multiplier)
        )

    def move_manual_actor(self, command: MoveManualActorCommand):
        return self._manual_actor_control_service.move(command)

    def interact_scene_object(self, command: InteractSceneObjectCommand):
        return self._manual_object_interaction_service.interact(command)
