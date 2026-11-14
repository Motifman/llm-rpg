from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.leaf_condition import LeafCondition
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ObjectStateKeyDeclaration,
    StateValue,
)
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import Count

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts


def _value_of(key: ObjectStateKeyDeclaration, facts: WorldFacts) -> StateValue:
    return facts.object_state(key.object_id).value_of(key, facts.now())


def _count_of(key: ObjectStateKeyDeclaration, facts: WorldFacts) -> Count:
    return facts.object_state(key.object_id).count_of(key, facts.now())


def _stock_of(key: ObjectStateKeyDeclaration, facts: WorldFacts) -> Count:
    return facts.object_state(key.object_id).stock_of(key, facts.now())


@final
@dataclass(frozen=True)
class ObjectValueIsCondition(LeafCondition):
    key: ObjectStateKeyDeclaration
    value: StateValue
    failure_text: TextWithUnassignedPeople | NoText

    def __post_init__(self) -> None:
        self.key.require_fits(self.value)

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return _value_of(self.key, facts) == self.value

    def _requirements_besides_text(self) -> Requirements:
        return Requirements.nothing()


@final
@dataclass(frozen=True)
class ObjectCountAtLeastCondition(LeafCondition):
    key: ObjectStateKeyDeclaration
    count: Count
    failure_text: TextWithUnassignedPeople | NoText

    def __post_init__(self) -> None:
        self.key.require_count()

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return _count_of(self.key, facts) >= self.count

    def _requirements_besides_text(self) -> Requirements:
        return Requirements.nothing()


@final
@dataclass(frozen=True)
class ObjectCountGreaterThanCondition(LeafCondition):
    key: ObjectStateKeyDeclaration
    other: ObjectStateKeyDeclaration
    failure_text: TextWithUnassignedPeople | NoText

    def __post_init__(self) -> None:
        self.key.require_count()
        self.other.require_count()

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return _count_of(self.key, facts) > _count_of(self.other, facts)

    def _requirements_besides_text(self) -> Requirements:
        return Requirements.nothing()


@final
@dataclass(frozen=True)
class ObjectStockAtLeastCondition(LeafCondition):
    key: ObjectStateKeyDeclaration
    amount: Count
    failure_text: TextWithUnassignedPeople | NoText

    def __post_init__(self) -> None:
        self.key.require_stock()

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return _stock_of(self.key, facts) >= self.amount

    def _requirements_besides_text(self) -> Requirements:
        return Requirements.nothing()
