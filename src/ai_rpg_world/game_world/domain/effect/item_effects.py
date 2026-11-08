from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import ItemSubject, Subject
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ItemSpecDeclaration,
    ItemStateKeyDeclaration,
    StateValue,
)
from ai_rpg_world.game_world.domain.exception.effect_exception import ArgumentIsNotAnItemException
from ai_rpg_world.game_world.domain.objects_and_items import PersonInventory
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.value_object import Count, PersonId
from ai_rpg_world.game_world.domain.value_object.argument_name import ArgumentName

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates


@final
@dataclass(frozen=True)
class GiveItemEffect:
    who: Subject
    item_spec: ItemSpecDeclaration
    count: Count

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        receiver = world.inventory(self.who.person_in(trigger))
        for _ in range(self.count.value):
            item = world.bring_item_into_world(self.item_spec, facts.now())
            receiver.receive(item, self.item_spec.item_spec_id)

    def requirements(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class TakeItemEffect:
    who: Subject
    item_spec: ItemSpecDeclaration
    count: Count

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        person = self.who.person_in(trigger)
        taken = facts.inventory(person).items_to_give_up(self.item_spec.item_spec_id, self.count)
        for item in taken:
            world.inventory(person).give_up(item)
            world.take_item_out_of_world(item)

    def requirements(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class InHands:
    def give_up(self, inventory: PersonInventory, item: ItemInstanceId) -> None:
        inventory.give_up_held(item)


@final
@dataclass(frozen=True)
class InPack:
    def give_up(self, inventory: PersonInventory, item: ItemInstanceId) -> None:
        inventory.give_up_packed(item)


@final
@dataclass(frozen=True)
class Anywhere:
    def give_up(self, inventory: PersonInventory, item: ItemInstanceId) -> None:
        inventory.give_up(item)


ItemPlace = InHands | InPack | Anywhere


@final
@dataclass(frozen=True)
class ItemByArgument:
    argument: ArgumentName
    place: ItemPlace

    def give_up_from(self, owner: PersonId, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> ItemInstanceId:
        item = trigger.argument(self.argument)
        if not isinstance(item, ItemInstanceId):
            raise ArgumentIsNotAnItemException(f"the argument {self.argument.value!r} holds {item!r}, not an item")
        self.place.give_up(world.inventory(owner), item)
        return item

    def requirements(self) -> Requirements:
        return replace(Requirements.nothing(), uses_action_arguments=frozenset({self.argument}))


@final
@dataclass(frozen=True)
class RandomItemOf:
    def give_up_from(self, owner: PersonId, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> ItemInstanceId:
        item = facts.inventory(owner).random_packed_item(facts.random())
        world.inventory(owner).give_up_packed(item)
        return item

    def requirements(self) -> Requirements:
        return replace(Requirements.nothing(), uses_chance=True)


@final
@dataclass(frozen=True)
class MoveItemEffect:
    from_who: Subject
    to_who: Subject
    item: ItemByArgument | RandomItemOf

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        moved = self.item.give_up_from(self.from_who.person_in(trigger), facts, world, trigger)
        world.inventory(self.to_who.person_in(trigger)).receive(moved, facts.item(moved).spec_id)

    def requirements(self) -> Requirements:
        return (
            self.from_who.requirements()
            .combined_with(self.to_who.requirements())
            .combined_with(self.item.requirements())
        )


@final
@dataclass(frozen=True)
class SetItemValueEffect:
    item: ItemSubject
    key: ItemStateKeyDeclaration
    value: StateValue

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.item(self.item.item_in(trigger)).set(self.key, self.value)

    def requirements(self) -> Requirements:
        return Requirements.nothing()
