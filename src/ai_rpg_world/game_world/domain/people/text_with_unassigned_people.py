from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypeVar, final

from ai_rpg_world.game_world.domain.people._person_placeholders import person_placeholders_in
from ai_rpg_world.game_world.domain.people.person_ref import PersonRef, Unidentified
from ai_rpg_world.game_world.domain.people.text_about_people import TextAboutPeople
from ai_rpg_world.game_world.domain.people.text_with_assigned_people import TextWithAssignedPeople
from ai_rpg_world.game_world.domain.value_object import PersonId

_Read = TypeVar("_Read")


@final
@dataclass(frozen=True)
class TextWithUnassignedPeople:
    template: str

    def __post_init__(self) -> None:
        person_placeholders_in(self.template)

    def placeholders(self) -> frozenset[str]:
        return person_placeholders_in(self.template)

    def explains(self) -> bool:
        return True

    def placeholders_read_as(self, read: Callable[[str, str], _Read]) -> frozenset[_Read]:
        return frozenset(read(placeholder, self.template) for placeholder in self.placeholders())

    def about_each(self, person_of: Callable[[str, str], PersonId]) -> TextAboutPeople:
        return self.about({placeholder: person_of(placeholder, self.template) for placeholder in self.placeholders()})

    def assign(self, people: Mapping[str, PersonRef | Unidentified]) -> TextWithAssignedPeople:
        return TextWithAssignedPeople(template=self.template, people=people)

    def about(self, people: Mapping[str, PersonId]) -> TextAboutPeople:
        return TextAboutPeople(template=self, people=people)
