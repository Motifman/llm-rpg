from __future__ import annotations

from typing import final

from ai_rpg_world.eventing import EventHandler
from ai_rpg_world.game_world.application.world_progress.withdraw_from_group_decisions import (
    WithdrawFromGroupDecisions,
    WithdrawFromGroupDecisionsCommand,
)
from ai_rpg_world.game_world.domain.person import PersonDiedEvent, PersonFellEvent


@final
class WithdrawFromGroupDecisionHandler(EventHandler[PersonFellEvent | PersonDiedEvent]):
    def __init__(self, withdraw_from_group_decisions: WithdrawFromGroupDecisions) -> None:
        self._withdraw_from_group_decisions = withdraw_from_group_decisions

    def handle(self, event: PersonFellEvent | PersonDiedEvent) -> None:
        self._withdraw_from_group_decisions(WithdrawFromGroupDecisionsCommand(event.person))
