from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import final

from ai_rpg_world.game_world.domain.exception.people_exception import PlaceholdersAndPeopleMismatchException
from ai_rpg_world.game_world.domain.people._person_placeholders import person_placeholders_in
from ai_rpg_world.game_world.domain.people.person_ref import PersonRef, Unidentified


@final
@dataclass(frozen=True)
class TextWithPeople:
    template: str
    people: Mapping[str, PersonRef | Unidentified]

    def __post_init__(self) -> None:
        placeholders = person_placeholders_in(self.template)
        if placeholders != set(self.people):
            raise PlaceholdersAndPeopleMismatchException(
                f"placeholders {sorted(placeholders)} and people {sorted(self.people)} differ in {self.template!r}"
            )
        object.__setattr__(self, "people", MappingProxyType(dict(self.people)))
