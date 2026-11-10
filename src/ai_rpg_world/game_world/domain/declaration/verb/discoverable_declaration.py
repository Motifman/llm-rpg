from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import final

from ai_rpg_world.game_world.domain.condition.condition import Condition
from ai_rpg_world.game_world.domain.effect.effect import Effect
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import PersonId, SpotId
from ai_rpg_world.game_world.domain.value_object.discoverable_id import DiscoverableId


class Finding(Enum):
    ONCE_IN_WORLD = "ONCE_IN_WORLD"
    ONCE_PER_PERSON = "ONCE_PER_PERSON"

    def is_found_by(self, person: PersonId, finders: frozenset[PersonId]) -> bool:
        if self is Finding.ONCE_IN_WORLD:
            return bool(finders)
        return person in finders

    def allows_finders(self, finders: frozenset[PersonId]) -> bool:
        return self is Finding.ONCE_PER_PERSON or len(finders) <= 1


@final
@dataclass(frozen=True)
class DiscoverableDeclaration:
    discoverable_id: DiscoverableId
    spot_id: SpotId
    found_text: TextWithUnassignedPeople
    condition: Condition
    when_found: Effect
    finding: Finding
