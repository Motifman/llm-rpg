from __future__ import annotations

from dataclasses import dataclass, field
from typing import final

from ai_rpg_world.game_world.domain.value_object import PersonId

# 同じ人がこの回数続けて選べなかったら、待つ人と同じ扱いにする (D1595、D2232 の 7 節)
_FAILURES_BEFORE_WAITING = 3


@final
@dataclass(frozen=True)
class FailuresByPerson:
    _counts: dict[PersonId, int] = field(default_factory=dict, hash=False)

    def failed(self, person: PersonId) -> FailuresByPerson:
        return FailuresByPerson({**self._counts, person: self._counts.get(person, 0) + 1})

    def cleared(self, person: PersonId) -> FailuresByPerson:
        return FailuresByPerson({p: n for p, n in self._counts.items() if p != person})

    def has_failed_enough_to_wait(self, person: PersonId) -> bool:
        return self._counts.get(person, 0) >= _FAILURES_BEFORE_WAITING
