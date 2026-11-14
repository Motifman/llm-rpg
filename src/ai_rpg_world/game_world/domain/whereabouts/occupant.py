from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.value_object import PersonId


@final
@dataclass(frozen=True)
class PersonBody:
    person: PersonId

    def is_departed(self) -> bool:
        return False

    def can_hold_items(self) -> bool:
        return True


@final
@dataclass(frozen=True)
class DepartedPerson:
    person: PersonId

    def is_departed(self) -> bool:
        return True

    def can_hold_items(self) -> bool:
        return False


Occupant = PersonBody | DepartedPerson
