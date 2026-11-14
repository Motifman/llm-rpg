from __future__ import annotations

from typing import final

from ai_rpg_world.eventing import EventHandler
from ai_rpg_world.game_world.application.person.decide_death_outcome import (
    DecideDeathOutcome,
    DecideDeathOutcomeCommand,
)
from ai_rpg_world.game_world.domain.person import PersonDiedEvent


@final
class DecideDeathOutcomeHandler(EventHandler[PersonDiedEvent]):
    def __init__(self, decide_death_outcome: DecideDeathOutcome) -> None:
        self._decide_death_outcome = decide_death_outcome

    def handle(self, event: PersonDiedEvent) -> None:
        self._decide_death_outcome(DecideDeathOutcomeCommand(event.person))
