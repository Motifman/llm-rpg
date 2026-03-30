"""Manual interaction entrypoint for a user-controlled actor."""

from __future__ import annotations

from typing import Iterable

from ai_rpg_world.application.ui.contracts.commands import InteractSceneObjectCommand
from ai_rpg_world.application.ui.contracts.interfaces import IManualInteractionPort
from ai_rpg_world.application.ui.exceptions import ManualControlForbiddenException


class ManualObjectInteractionService:
    def __init__(
        self,
        interaction_port: IManualInteractionPort,
        *,
        manual_player_ids: Iterable[int],
    ) -> None:
        self._interaction_port = interaction_port
        self._manual_player_ids = set(manual_player_ids)

    def interact(self, command: InteractSceneObjectCommand):
        if command.player_id not in self._manual_player_ids:
            raise ManualControlForbiddenException(command.player_id)
        return self._interaction_port.interact(
            actor_id=command.player_id,
            target_object_id=command.target_object_id,
        )
