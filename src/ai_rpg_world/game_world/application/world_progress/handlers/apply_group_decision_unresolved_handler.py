from __future__ import annotations

from typing import final

from ai_rpg_world.eventing import EventHandler
from ai_rpg_world.game_world.application.world_progress.apply_group_decision_result import (
    ApplyGroupDecisionUnresolved,
    ApplyGroupDecisionUnresolvedCommand,
)
from ai_rpg_world.game_world.domain.world_progress import GroupDecisionUnresolvedEvent


@final
class ApplyGroupDecisionUnresolvedHandler(EventHandler[GroupDecisionUnresolvedEvent]):
    def __init__(self, apply_group_decision_unresolved: ApplyGroupDecisionUnresolved) -> None:
        self._apply_group_decision_unresolved = apply_group_decision_unresolved

    def handle(self, event: GroupDecisionUnresolvedEvent) -> None:
        self._apply_group_decision_unresolved(ApplyGroupDecisionUnresolvedCommand(event.decision_id))
