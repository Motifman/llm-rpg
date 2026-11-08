from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.eventing import new_event_stamp
from ai_rpg_world.eventing.aggregate_root import AggregateRoot
from ai_rpg_world.eventing.domain_event import DomainEvent
from ai_rpg_world.game_world.domain.exception.objects_and_items_exception import (
    InventoryFullException,
    ItemAlreadyCarriedException,
    ItemNotCarriedException,
    NotEnoughItemsOfSpecException,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.value_object import Capacity, Count, Gold, HandsNeeded, ItemSpecId, PersonId

_HANDS = 2


@final
@dataclass(frozen=True, kw_only=True)
class ItemReceivedEvent(DomainEvent):
    person: PersonId
    item: ItemInstanceId


@final
@dataclass(frozen=True, kw_only=True)
class ItemGivenUpEvent(DomainEvent):
    person: PersonId
    item: ItemInstanceId
    was_held: bool


@final
@dataclass(frozen=True, kw_only=True)
class ItemHeldEvent(DomainEvent):
    person: PersonId
    item: ItemInstanceId


@final
@dataclass(frozen=True, kw_only=True)
class ItemPutAwayEvent(DomainEvent):
    person: PersonId
    item: ItemInstanceId


@final
@dataclass(frozen=True, kw_only=True)
class GoldEarnedEvent(DomainEvent):
    person: PersonId
    amount: Gold
    before: Gold
    after: Gold


@final
@dataclass(frozen=True, kw_only=True)
class GoldPaidEvent(DomainEvent):
    person: PersonId
    amount: Gold
    before: Gold
    after: Gold


PersonInventoryEvent = (
    ItemReceivedEvent | ItemGivenUpEvent | ItemHeldEvent | ItemPutAwayEvent | GoldEarnedEvent | GoldPaidEvent
)


@final
@dataclass(frozen=True)
class _HeldItem:
    item: ItemInstanceId
    hands_needed: HandsNeeded


class PersonInventory(AggregateRoot[PersonInventoryEvent]):
    def __init__(self, person_id: PersonId, capacity: Capacity) -> None:
        super().__init__()
        self._person_id = person_id
        self._capacity = capacity
        self._packed: list[ItemInstanceId] = []
        self._held: list[_HeldItem] = []
        self._specs: dict[ItemInstanceId, ItemSpecId] = {}
        self._gold = Gold(0)

    @property
    def person_id(self) -> PersonId:
        return self._person_id

    def receive(self, item: ItemInstanceId, spec: ItemSpecId) -> None:
        if self._carries(item):
            raise ItemAlreadyCarriedException(f"{self._person_id.value} already carries {item.value}")
        if self.is_full():
            raise InventoryFullException(f"{self._person_id.value} cannot carry more than {self._capacity.value} items")
        self._packed.append(item)
        self._specs[item] = spec
        self.add_event(ItemReceivedEvent(**new_event_stamp(), person=self._person_id, item=item))

    def give_up(self, item: ItemInstanceId) -> None:
        self._require_carried(item)
        was_held = self._is_held(item)
        if was_held:
            self._held = [held for held in self._held if held.item != item]
        else:
            self._packed.remove(item)
        del self._specs[item]
        self.add_event(ItemGivenUpEvent(**new_event_stamp(), person=self._person_id, item=item, was_held=was_held))

    def hold(self, item: ItemInstanceId, hands_needed: HandsNeeded) -> None:
        self._require_carried(item)
        if self._is_held(item):
            return
        while _HANDS - self._hands_in_use() < hands_needed.value:
            self.put_away(self._held[0].item)
        self._packed.remove(item)
        self._held.append(_HeldItem(item, hands_needed))
        self.add_event(ItemHeldEvent(**new_event_stamp(), person=self._person_id, item=item))

    def put_away(self, item: ItemInstanceId) -> None:
        self._require_carried(item)
        if not self._is_held(item):
            return
        self._held = [held for held in self._held if held.item != item]
        self._packed.append(item)
        self.add_event(ItemPutAwayEvent(**new_event_stamp(), person=self._person_id, item=item))

    def earn(self, amount: Gold) -> None:
        if amount == Gold(0):
            return
        before = self._gold
        self._gold = before + amount
        self.add_event(
            GoldEarnedEvent(**new_event_stamp(), person=self._person_id, amount=amount, before=before, after=self._gold)
        )

    def pay(self, amount: Gold) -> None:
        if amount == Gold(0):
            return
        before = self._gold
        self._gold = before - amount
        self.add_event(
            GoldPaidEvent(**new_event_stamp(), person=self._person_id, amount=amount, before=before, after=self._gold)
        )

    def items(self) -> tuple[ItemInstanceId, ...]:
        return self.held_items() + self.packed_items()

    def held_items(self) -> tuple[ItemInstanceId, ...]:
        return tuple(held.item for held in self._held)

    def packed_items(self) -> tuple[ItemInstanceId, ...]:
        return tuple(self._packed)

    def is_full(self) -> bool:
        return len(self._packed) + len(self._held) >= self._capacity.value

    def available_gold(self) -> Gold:
        return self._gold

    def count_of(self, spec: ItemSpecId) -> Count:
        return Count(len(self._items_of(spec)))

    def items_to_give_up(self, spec: ItemSpecId, count: Count) -> tuple[ItemInstanceId, ...]:
        candidates = self._items_of(spec)
        if len(candidates) < count.value:
            raise NotEnoughItemsOfSpecException(
                f"{self._person_id.value} carries {len(candidates)} of {spec.value}, cannot give up {count.value}"
            )
        return candidates[: count.value]

    def _items_of(self, spec: ItemSpecId) -> tuple[ItemInstanceId, ...]:
        return tuple(item for item in self.packed_items() + self.held_items() if self._specs[item] == spec)

    def _carries(self, item: ItemInstanceId) -> bool:
        return item in self._packed or self._is_held(item)

    def _is_held(self, item: ItemInstanceId) -> bool:
        return any(held.item == item for held in self._held)

    def _require_carried(self, item: ItemInstanceId) -> None:
        if not self._carries(item):
            raise ItemNotCarriedException(f"{self._person_id.value} does not carry {item.value}")

    def _hands_in_use(self) -> int:
        return sum(held.hands_needed.value for held in self._held)
