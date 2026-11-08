from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.people._person_placeholders import person_placeholders_in
from ai_rpg_world.game_world.domain.people.person_ref import PersonRef, Unidentified
from ai_rpg_world.game_world.domain.people.text_about_people import TextAboutPeople
from ai_rpg_world.game_world.domain.people.text_with_assigned_people import TextWithAssignedPeople
from ai_rpg_world.game_world.domain.value_object import PersonId


@final
@dataclass(frozen=True)
class TextWithUnassignedPeople:
    template: str

    def __post_init__(self) -> None:
        person_placeholders_in(self.template)

    def placeholders(self) -> frozenset[str]:
        return person_placeholders_in(self.template)

    def assign(self, people: Mapping[str, PersonRef | Unidentified]) -> TextWithAssignedPeople:
        return TextWithAssignedPeople(template=self.template, people=people)

    def about(self, people: Mapping[str, PersonId]) -> TextAboutPeople:
        return TextAboutPeople(template=self, people=people)
