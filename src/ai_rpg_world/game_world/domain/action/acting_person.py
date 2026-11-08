from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.person import FallCause, StruckByPerson, WorldHappening
from ai_rpg_world.game_world.domain.value_object import PersonId


@final
@dataclass(frozen=True)
class NoActingPerson:
    pass


def fall_cause_from(acting_person: PersonId | NoActingPerson, victim: PersonId) -> FallCause:
    if isinstance(acting_person, PersonId) and acting_person != victim:
        return StruckByPerson(acting_person)
    return WorldHappening()
