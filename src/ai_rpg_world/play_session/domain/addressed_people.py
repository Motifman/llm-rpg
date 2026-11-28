from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.value_object import PersonId


@final
@dataclass(frozen=True)
class AddressedPeople:
    _people: frozenset[PersonId] = frozenset()

    def with_person(self, person: PersonId) -> AddressedPeople:
        return AddressedPeople(self._people | {person})

    def without(self, person: PersonId) -> AddressedPeople:
        return AddressedPeople(self._people - {person})

    def only(self, people: Iterable[PersonId]) -> AddressedPeople:
        return AddressedPeople(self._people & frozenset(people))

    def __contains__(self, person: object) -> bool:
        return person in self._people
