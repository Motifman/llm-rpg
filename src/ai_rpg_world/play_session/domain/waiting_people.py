from __future__ import annotations

from dataclasses import dataclass, field
from typing import final

from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.play_session.domain.turn_skip import TurnSkipReason


@final
@dataclass(frozen=True)
class _Waiting:
    since_round: int
    reason: TurnSkipReason


@final
@dataclass(frozen=True)
class WaitingPeople:
    _by_person: dict[PersonId, _Waiting] = field(default_factory=dict, hash=False)

    def started(self, person: PersonId, round_number: int, reason: TurnSkipReason) -> WaitingPeople:
        return WaitingPeople({**self._by_person, person: _Waiting(round_number, reason)})

    def woken(self, person: PersonId) -> WaitingPeople:
        return WaitingPeople({p: w for p, w in self._by_person.items() if p != person})

    def woken_after(self, current_round: int, rounds_to_wait: int) -> WaitingPeople:
        return WaitingPeople(
            {p: w for p, w in self._by_person.items() if current_round - w.since_round <= rounds_to_wait}
        )

    def reason_of(self, person: PersonId) -> TurnSkipReason | None:
        waiting = self._by_person.get(person)
        return None if waiting is None else waiting.reason
