from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.exception.people_exception import PlaceholdersAndPeopleMismatchException
from ai_rpg_world.game_world.domain.people.people_as_seen import PeopleAsSeen
from ai_rpg_world.game_world.domain.people.person_ref import Unidentified
from ai_rpg_world.game_world.domain.people.text_with_assigned_people import TextWithAssignedPeople
from ai_rpg_world.game_world.domain.value_object import PersonId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.people.text_with_unassigned_people import TextWithUnassignedPeople


@final
@dataclass(frozen=True)
class TextAboutPeople:
    template: TextWithUnassignedPeople
    people: Mapping[str, PersonId]

    def __post_init__(self) -> None:
        placeholders = self.template.placeholders()
        if placeholders != set(self.people):
            raise PlaceholdersAndPeopleMismatchException(
                f"placeholders {sorted(placeholders)} and people {sorted(self.people)} differ"
                f" in {self.template.template!r}"
            )
        object.__setattr__(self, "people", MappingProxyType(dict(self.people)))

    def seen_by(self, view: PeopleAsSeen) -> TextWithAssignedPeople:
        return self.template.assign({key: view.ref_of(person) for key, person in self.people.items()})

    def unidentified(self) -> TextWithAssignedPeople:
        return self.template.assign({key: Unidentified() for key in self.people})
