from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.people.person_ref import NoVisibleName, PersonRef
from ai_rpg_world.game_world.domain.value_object import DisplayName, PersonId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.condition.aggregate_readings import PeopleRegisterReading


@final
@dataclass(frozen=True)
class PeopleSeenBy:
    viewer: PersonId
    register: PeopleRegisterReading
    name_tags: bool
    knows_at_start: frozenset[PersonId]

    def ref_of(self, person: PersonId) -> PersonRef:
        return PersonRef(
            handle=self.register.handle_of(person),
            appearance=self.register.appearance_of(person),
            visible_name=self._visible_name_of(person),
        )

    def _visible_name_of(self, person: PersonId) -> DisplayName | NoVisibleName:
        if self.name_tags or person == self.viewer or person in self.knows_at_start:
            return self.register.name_of(person)
        return NoVisibleName()
