"""Manual control entrypoint for a single user-controlled actor."""

from __future__ import annotations

from typing import Iterable

from ai_rpg_world.application.ui.contracts.commands import MoveManualActorCommand
from ai_rpg_world.application.ui.contracts.interfaces import IManualMovementPort
from ai_rpg_world.application.ui.exceptions import ManualControlForbiddenException
from ai_rpg_world.application.ui.services.game_scene_projection import GameSceneProjection
from ai_rpg_world.application.world.contracts.commands import MoveTileCommand


class ManualActorControlService:
    """Wraps existing movement service for UI-driven manual tile stepping."""

    def __init__(
        self,
        movement_port: IManualMovementPort,
        projection: GameSceneProjection,
        *,
        manual_player_ids: Iterable[int],
    ) -> None:
        self._movement_port = movement_port
        self._projection = projection
        self._manual_player_ids = set(manual_player_ids)
        for player_id in self._manual_player_ids:
            self._projection.set_actor_control_flags(
                actor_id=player_id,
                is_manual_controlled=True,
                is_llm_controlled=False,
            )

    def move(self, command: MoveManualActorCommand):
        if command.player_id not in self._manual_player_ids:
            raise ManualControlForbiddenException(command.player_id)
        self._projection.set_actor_control_flags(
            actor_id=command.player_id,
            is_manual_controlled=True,
            is_llm_controlled=False,
        )
        return self._movement_port.move_tile(
            MoveTileCommand(
                player_id=command.player_id,
                direction=command.direction,
            )
        )
