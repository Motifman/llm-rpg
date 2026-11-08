from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.action.action_arguments import TextArgumentValue
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import Subject
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ItemSpecDeclaration,
    ObjectStateKeyDeclaration,
    StateValue,
    TextBody,
)
from ai_rpg_world.game_world.domain.declaration.object_and_item.object_declaration import ObjectDeclaration
from ai_rpg_world.game_world.domain.exception.effect_exception import (
    ArgumentIsNotTextException,
    TextHasNoAuthorException,
)
from ai_rpg_world.game_world.domain.value_object import Count, Gold, PersonId
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates


@final
@dataclass(frozen=True)
class SetObjectValueEffect:
    key: ObjectStateKeyDeclaration
    value: StateValue

    def __post_init__(self) -> None:
        self.key.require_fits(self.value)

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.object_state(self.key.object_id).set(self.key, self.value, facts.now())

    def requirements(self) -> Requirements:
        return Requirements.nothing()


@final
@dataclass(frozen=True)
class AddToObjectCountEffect:
    key: ObjectStateKeyDeclaration
    amount: Count

    def __post_init__(self) -> None:
        self.key.require_count()

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.object_state(self.key.object_id).add_to_count(self.key, self.amount)

    def requirements(self) -> Requirements:
        return Requirements.nothing()


@final
@dataclass(frozen=True)
class SubtractFromObjectCountEffect:
    key: ObjectStateKeyDeclaration
    amount: Count

    def __post_init__(self) -> None:
        self.key.require_count()

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.object_state(self.key.object_id).subtract_from_count(self.key, self.amount)

    def requirements(self) -> Requirements:
        return Requirements.nothing()


@final
@dataclass(frozen=True)
class TakeFromObjectStockEffect:
    key: ObjectStateKeyDeclaration
    amount: Count

    def __post_init__(self) -> None:
        self.key.require_stock()

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.object_state(self.key.object_id).take_from_stock(self.key, self.amount, facts.now())

    def requirements(self) -> Requirements:
        return Requirements.nothing()


@final
@dataclass(frozen=True)
class WriteTextEffect:
    key: ObjectStateKeyDeclaration
    body_argument: ArgumentName

    def __post_init__(self) -> None:
        self.key.require_written_text()

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        body = trigger.argument(self.body_argument)
        if not isinstance(body, TextArgumentValue):
            raise ArgumentIsNotTextException(f"the argument {self.body_argument.value!r} holds {body!r}, not text")
        author = trigger.acting_person()
        if not isinstance(author, PersonId):
            raise TextHasNoAuthorException(f"{trigger!r} has no one acting to write {self.key.key.value!r}")
        world.object_state(self.key.object_id).write_text(self.key, TextBody(body.text), author, facts.now())

    def requirements(self) -> Requirements:
        return replace(Requirements.nothing(), uses_action_arguments=frozenset({self.body_argument}))


@final
@dataclass(frozen=True)
class RevealObjectEffect:
    obj: ObjectDeclaration

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.object_state(self.obj.object_id).reveal()

    def requirements(self) -> Requirements:
        return Requirements.nothing()


@final
@dataclass(frozen=True)
class DepositItemToObjectEffect:
    who: Subject
    item_spec: ItemSpecDeclaration
    key: ObjectStateKeyDeclaration

    def __post_init__(self) -> None:
        self.key.require_count()

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        person = self.who.person_in(trigger)
        (deposited,) = facts.inventory(person).items_to_give_up(self.item_spec.item_spec_id, Count(1))
        world.inventory(person).give_up(deposited)
        world.take_item_out_of_world(deposited)
        world.object_state(self.key.object_id).add_to_count(self.key, Count(1))

    def requirements(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class DepositGoldToObjectEffect:
    who: Subject
    amount: Gold
    key: ObjectStateKeyDeclaration

    def __post_init__(self) -> None:
        self.key.require_count()

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.inventory(self.who.person_in(trigger)).pay(self.amount)
        world.object_state(self.key.object_id).add_to_count(self.key, Count(self.amount.value))

    def requirements(self) -> Requirements:
        return self.who.requirements()
