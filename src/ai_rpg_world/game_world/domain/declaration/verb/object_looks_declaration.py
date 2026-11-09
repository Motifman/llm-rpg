from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.action.trigger import LookingAround
from ai_rpg_world.game_world.domain.condition.condition import Condition
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.value_object import DescriptionText, ObjectId


@final
@dataclass(frozen=True)
class NoLook:
    pass


@final
@dataclass(frozen=True)
class ObjectLook:
    when: Condition
    text: DescriptionText


@final
@dataclass(frozen=True)
class ObjectLooksDeclaration:
    object_id: ObjectId
    looks: tuple[ObjectLook, ...]

    def look_now(self, facts: WorldFacts) -> DescriptionText | NoLook:
        looking_around = LookingAround(facts.now())
        for look in self.looks:
            if look.when.holds(facts, looking_around):
                return look.text
        return NoLook()
