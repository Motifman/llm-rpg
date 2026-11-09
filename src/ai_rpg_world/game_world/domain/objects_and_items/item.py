from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.eventing import new_event_stamp
from ai_rpg_world.eventing.aggregate_root import AggregateRoot
from ai_rpg_world.eventing.domain_event import DomainEvent
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ItemSpecDeclaration,
    ItemStateKeyDeclaration,
    Lasts,
    LitWhen,
    StateValue,
)
from ai_rpg_world.game_world.domain.exception.object_and_item_exception import StateValueMismatchesKindException
from ai_rpg_world.game_world.domain.exception.objects_and_items_exception import (
    ItemAlreadyLeftWorldException,
    ItemDoesNotRunOutException,
    ItemHasNotRunOutException,
    StateKeyNotOwnedException,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.objects_and_items.where_item_was import WhereItemWas
from ai_rpg_world.game_world.domain.value_object import ItemSpecId, StateKeyId, Ticks, WorldTick


@final
@dataclass(frozen=True, kw_only=True)
class ItemCameIntoWorldEvent(DomainEvent):
    item: ItemInstanceId
    spec_id: ItemSpecId
    came_at: WorldTick


@final
@dataclass(frozen=True, kw_only=True)
class ItemStateChangedEvent(DomainEvent):
    item: ItemInstanceId
    key: StateKeyId
    before: StateValue
    after: StateValue


@final
@dataclass(frozen=True, kw_only=True)
class ItemLeftWorldEvent(DomainEvent):
    item: ItemInstanceId


@final
@dataclass(frozen=True, kw_only=True)
class ItemRanOutEvent(DomainEvent):
    item: ItemInstanceId
    spec_id: ItemSpecId
    where: WhereItemWas
    at: WorldTick


ItemEvent = ItemCameIntoWorldEvent | ItemStateChangedEvent | ItemLeftWorldEvent | ItemRanOutEvent


class Item(AggregateRoot[ItemEvent]):
    def __init__(self, item_id: ItemInstanceId, spec: ItemSpecDeclaration, came_at: WorldTick) -> None:
        super().__init__()
        self._item_id = item_id
        self._spec = spec
        self._came_at = came_at
        self._values: dict[StateKeyId, StateValue] = {state_key.key: state_key.initial for state_key in spec.state_keys}
        self._in_world = True

    @classmethod
    def come_into_world(cls, item_id: ItemInstanceId, spec: ItemSpecDeclaration, now: WorldTick) -> Item:
        item = cls(item_id, spec, now)
        item.add_event(
            ItemCameIntoWorldEvent(**new_event_stamp(), item=item_id, spec_id=spec.item_spec_id, came_at=now)
        )
        return item

    @property
    def item_id(self) -> ItemInstanceId:
        return self._item_id

    @property
    def spec_id(self) -> ItemSpecId:
        return self._spec.item_spec_id

    def set(self, key: ItemStateKeyDeclaration, value: StateValue) -> None:
        if not self._in_world:
            raise ItemAlreadyLeftWorldException(f"{self._item_id.value} has left the world")
        before = self.value_of(key)
        if not key.kind.accepts(value):
            raise StateValueMismatchesKindException(
                f"{value!r} does not fit {key.kind!r} of {self._item_id.value}.{key.key.value}"
            )
        if value == before:
            return
        self._values[key.key] = value
        self.add_event(
            ItemStateChangedEvent(**new_event_stamp(), item=self._item_id, key=key.key, before=before, after=value)
        )

    def leave_world(self) -> None:
        if not self._in_world:
            return
        self._in_world = False
        self.add_event(ItemLeftWorldEvent(**new_event_stamp(), item=self._item_id))

    def run_out(self, now: WorldTick, where: WhereItemWas) -> None:
        if not self._in_world:
            return
        lasts = self._spec.lasts
        if not isinstance(lasts, Lasts):
            raise ItemDoesNotRunOutException(f"{self._item_id.value} lasts indefinitely")
        if not self._came_at.has_passed(lasts.ticks, now):
            raise ItemHasNotRunOutException(
                f"{self._item_id.value} lasts {lasts.ticks.value} ticks and is {self.age(now).value} ticks old"
            )
        self._in_world = False
        self.add_event(
            ItemRanOutEvent(**new_event_stamp(), item=self._item_id, spec_id=self.spec_id, where=where, at=now)
        )

    def value_of(self, key: ItemStateKeyDeclaration) -> StateValue:
        if key not in self._spec.state_keys:
            raise StateKeyNotOwnedException(
                f"{self._item_id.value} does not have {key.item_spec_id.value}.{key.key.value}"
            )
        return self._values[key.key]

    def age(self, now: WorldTick) -> Ticks:
        return now.ticks_since(self._came_at)

    def gives_light(self) -> bool:
        lights_up = self._spec.lights_up
        return isinstance(lights_up, LitWhen) and self._values[lights_up.key] == lights_up.value
