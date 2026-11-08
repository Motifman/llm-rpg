from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.exception.character_exception import (
    DuplicatedInitialGroupException,
    DuplicatedKnownPersonException,
    HeldItemNotAmongInitialItemsException,
)
from ai_rpg_world.game_world.domain.value_object import (
    Capacity,
    DescriptionText,
    GroupId,
    HitPoints,
    ItemSpecId,
    PersonId,
    SpotId,
)


@final
@dataclass(frozen=True)
class UsesWorldDefault:
    pass


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
    max_hp: HitPoints | UsesWorldDefault
    pack_capacity: Capacity | UsesWorldDefault

    def __post_init__(self) -> None:
        not_carried = Counter(self.initial_held) - Counter(self.initial_items)
        if not_carried:
            raise HeldItemNotAmongInitialItemsException(
                f"{self.person_id.value} holds items not among initial_items: "
                f"{sorted(item.value for item in not_carried.elements())}"
            )
        duplicated_groups = _listed_more_than_once(group.value for group in self.initial_groups)
        if duplicated_groups:
            raise DuplicatedInitialGroupException(
                f"{self.person_id.value} lists initial_groups more than once: {duplicated_groups}"
            )
        duplicated_people = _listed_more_than_once(person.value for person in self.knows_at_start)
        if duplicated_people:
            raise DuplicatedKnownPersonException(
                f"{self.person_id.value} lists knows_at_start more than once: {duplicated_people}"
            )

    def starting_hp(self, world_default: HitPoints) -> HitPoints:
        return world_default if isinstance(self.max_hp, UsesWorldDefault) else self.max_hp

    def starting_pack_capacity(self, world_default: Capacity) -> Capacity:
        return world_default if isinstance(self.pack_capacity, UsesWorldDefault) else self.pack_capacity


def _listed_more_than_once(names: Iterable[str]) -> list[str]:
    return sorted(name for name, count in Counter(names).items() if count > 1)
