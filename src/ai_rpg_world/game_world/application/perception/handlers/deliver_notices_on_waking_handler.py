from __future__ import annotations

from typing import final

from ai_rpg_world.eventing import EventHandler
from ai_rpg_world.game_world.application.deliver_notices_on_waking import (
    DeliverNoticesOnWaking,
    DeliverNoticesOnWakingCommand,
)
from ai_rpg_world.game_world.domain.person import PersonRevivedEvent


@final
class DeliverNoticesOnWakingHandler(EventHandler[PersonRevivedEvent]):
    def __init__(self, deliver_notices_on_waking: DeliverNoticesOnWaking) -> None:
        self._deliver_notices_on_waking = deliver_notices_on_waking

    def handle(self, event: PersonRevivedEvent) -> None:
        self._deliver_notices_on_waking(DeliverNoticesOnWakingCommand(person=event.person, at=event.revived_at))
