from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.value_object import PersonId


@final
@dataclass(frozen=True)
class PersonBody:
    person: PersonId


@final
@dataclass(frozen=True)
class DepartedPerson:
    person: PersonId


Occupant = PersonBody | DepartedPerson
