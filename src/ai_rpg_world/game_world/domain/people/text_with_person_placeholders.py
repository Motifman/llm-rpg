from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.people._person_placeholders import person_placeholders_in
from ai_rpg_world.game_world.domain.people.person_ref import PersonRef, Unidentified
from ai_rpg_world.game_world.domain.people.text_with_people import TextWithPeople


@final
@dataclass(frozen=True)
class TextWithPersonPlaceholders:
    template: str

    def __post_init__(self) -> None:
        person_placeholders_in(self.template)

    def placeholders(self) -> frozenset[str]:
        return person_placeholders_in(self.template)

    def fill(self, people: Mapping[str, PersonRef | Unidentified]) -> TextWithPeople:
        return TextWithPeople(template=self.template, people=people)
