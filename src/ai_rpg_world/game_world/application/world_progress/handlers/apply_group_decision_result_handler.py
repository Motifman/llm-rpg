from __future__ import annotations

from typing import final

from ai_rpg_world.eventing import EventHandler
from ai_rpg_world.game_world.application.world_progress.apply_group_decision_result import (
    ApplyGroupDecisionReached,
    ApplyGroupDecisionReachedCommand,
    ApplyGroupDecisionUnresolved,
    ApplyGroupDecisionUnresolvedCommand,
)
from ai_rpg_world.game_world.domain.world_progress import GroupDecisionReachedEvent, GroupDecisionUnresolvedEvent


@final
class ApplyGroupDecisionResultHandler(EventHandler[GroupDecisionReachedEvent | GroupDecisionUnresolvedEvent]):
    def __init__(self, reached: ApplyGroupDecisionReached, unresolved: ApplyGroupDecisionUnresolved) -> None:
        self._reached = reached
        self._unresolved = unresolved

    def handle(self, event: GroupDecisionReachedEvent | GroupDecisionUnresolvedEvent) -> None:
        if isinstance(event, GroupDecisionReachedEvent):
            self._reached(ApplyGroupDecisionReachedCommand(event.decision_id, event.chosen))
        else:
            self._unresolved(ApplyGroupDecisionUnresolvedCommand(event.decision_id))
