from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import final

from ai_rpg_world.game_world.domain.exception.people_exception import HolesAndPeopleMismatchException
from ai_rpg_world.game_world.domain.people._person_holes import person_holes_in
from ai_rpg_world.game_world.domain.people.person_ref import PersonRef, Unidentified


@final
@dataclass(frozen=True)
class TextWithPeople:
    template: str
    people: Mapping[str, PersonRef | Unidentified]

    def __post_init__(self) -> None:
        holes = person_holes_in(self.template)
        if holes != set(self.people):
            raise HolesAndPeopleMismatchException(
                f"holes {sorted(holes)} and people {sorted(self.people)} differ in {self.template!r}"
            )
        object.__setattr__(self, "people", MappingProxyType(dict(self.people)))
