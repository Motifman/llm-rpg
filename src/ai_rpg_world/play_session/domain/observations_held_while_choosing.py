from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import final

from ai_rpg_world.being.contract import Observation
from ai_rpg_world.game_world.domain.value_object import PersonId


@final
@dataclass(frozen=True)
class ObservationsHeldWhileChoosing:
    _choosing: frozenset[PersonId] = frozenset()
    _held: dict[PersonId, tuple[Observation, ...]] = field(default_factory=dict, hash=False)

    def began(self, people: Iterable[PersonId]) -> ObservationsHeldWhileChoosing:
        return ObservationsHeldWhileChoosing(self._choosing | frozenset(people), self._held)

    def finished_choosing(self, person: PersonId) -> ObservationsHeldWhileChoosing:
        return ObservationsHeldWhileChoosing(self._choosing - {person}, self._held)

    def is_choosing(self, person: PersonId) -> bool:
        return person in self._choosing

    def hold(self, person: PersonId, observation: Observation) -> ObservationsHeldWhileChoosing:
        return ObservationsHeldWhileChoosing(
            self._choosing, {**self._held, person: (*self._held.get(person, ()), observation)}
        )

    def held_for(self, person: PersonId) -> tuple[Observation, ...]:
        return self._held.get(person, ())

    def released(self, person: PersonId) -> ObservationsHeldWhileChoosing:
        return ObservationsHeldWhileChoosing(
            self._choosing - {person}, {p: o for p, o in self._held.items() if p != person}
        )
