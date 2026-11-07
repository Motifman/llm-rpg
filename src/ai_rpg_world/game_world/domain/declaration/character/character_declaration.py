from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.exception.character_exception import HeldItemNotAmongInitialItemsException
from ai_rpg_world.game_world.domain.value_object import DescriptionText, GroupId, ItemSpecId, PersonId, SpotId


@final
@dataclass(frozen=True)
class CharacterDeclaration:
    person_id: PersonId
    appearance: DescriptionText
    spawn_spot: SpotId
    initial_items: tuple[ItemSpecId, ...]
    initial_held: tuple[ItemSpecId, ...]
    initial_groups: tuple[GroupId, ...]
    knows_at_start: tuple[PersonId, ...]

    def __post_init__(self) -> None:
        not_carried = Counter(self.initial_held) - Counter(self.initial_items)
        if not_carried:
            raise HeldItemNotAmongInitialItemsException(
                f"{self.person_id.value} holds items not among initial_items: "
                f"{sorted(item.value for item in not_carried.elements())}"
            )
