from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.play_session.domain.play_session_exception import TurnNotDueException


@final
@dataclass(frozen=True)
class OpenRound:
    number: int
    due: tuple[PersonId, ...]
    finished: tuple[PersonId, ...] = ()

    def remaining(self) -> tuple[PersonId, ...]:
        return tuple(person for person in self.due if person not in self.finished)

    def check_turn_left(self, person: PersonId) -> None:
        if person not in self.remaining():
            raise TurnNotDueException(f"{person.value} has no turn left in round {self.number}")

    def finished_by(self, person: PersonId) -> OpenRound:
        self.check_turn_left(person)
        return OpenRound(self.number, self.due, (*self.finished, person))

    @property
    def last_order(self) -> int:
        return len(self.finished)
