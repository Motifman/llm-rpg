from __future__ import annotations

from typing import final

from ai_rpg_world.eventing import EventHandler
from ai_rpg_world.game_world.application.deliver_notices_on_leaving import (
    DeliverNoticesOnLeaving,
    DeliverNoticesOnLeavingCommand,
)
from ai_rpg_world.game_world.domain.person import PersonOutcomeDecidedEvent


@final
class DeliverNoticesOnLeavingHandler(EventHandler[PersonOutcomeDecidedEvent]):
    def __init__(self, deliver_notices_on_leaving: DeliverNoticesOnLeaving) -> None:
        self._deliver_notices_on_leaving = deliver_notices_on_leaving

    def handle(self, event: PersonOutcomeDecidedEvent) -> None:
        self._deliver_notices_on_leaving(
            DeliverNoticesOnLeavingCommand(person=event.person, outcome=event.outcome, at=event.at)
        )
