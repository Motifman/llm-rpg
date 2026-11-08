from __future__ import annotations

from typing import Protocol

from ai_rpg_world.game_world.domain.people.person_ref import PersonRef
from ai_rpg_world.game_world.domain.value_object import PersonId


class PeopleAsSeen(Protocol):
    def ref_of(self, person: PersonId) -> PersonRef: ...
