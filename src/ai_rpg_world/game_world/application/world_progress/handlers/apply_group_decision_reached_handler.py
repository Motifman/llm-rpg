from __future__ import annotations

from typing import final

from ai_rpg_world.eventing import EventHandler
from ai_rpg_world.game_world.application.world_progress.apply_group_decision_result import (
    ApplyGroupDecisionReached,
    ApplyGroupDecisionReachedCommand,
)
from ai_rpg_world.game_world.domain.world_progress import GroupDecisionReachedEvent


@final
class ApplyGroupDecisionReachedHandler(EventHandler[GroupDecisionReachedEvent]):
    def __init__(self, apply_group_decision_reached: ApplyGroupDecisionReached) -> None:
        self._apply_group_decision_reached = apply_group_decision_reached

    def handle(self, event: GroupDecisionReachedEvent) -> None:
        self._apply_group_decision_reached(ApplyGroupDecisionReachedCommand(event.decision_id, event.chosen))
