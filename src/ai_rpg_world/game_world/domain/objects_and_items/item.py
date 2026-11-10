from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.eventing import new_event_stamp
from ai_rpg_world.eventing.aggregate_root import AggregateRoot
from ai_rpg_world.eventing.domain_event import DomainEvent
from ai_rpg_world.game_world.domain.declaration.object_and_item import (
    ItemSpecDeclaration,
    ItemStateKeyDeclaration,
    LitWhen,
    StateValue,
)
from ai_rpg_world.game_world.domain.exception.game_world_exception import (
    MementoDoesNotMatchDesignException,
    RepeatedMementoKeyException,
)
from ai_rpg_world.game_world.domain.exception.object_and_item_declaration_exception import (
    StateValueMismatchesKindException,
)
from ai_rpg_world.game_world.domain.exception.objects_and_items_exception import (
    ItemAlreadyLeftWorldException,
    StateKeyNotOwnedException,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.objects_and_items.where_item_was import WhereItemWas
from ai_rpg_world.game_world.domain.value_object import ItemSpecId, StateKeyId, Ticks, WorldTick

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign


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


@final
@dataclass(frozen=True)
class ItemStateKeyValue:
    key: StateKeyId
    value: StateValue


@final
@dataclass(frozen=True)
class ItemMemento:
    item_id: ItemInstanceId
    spec_id: ItemSpecId
    came_at: WorldTick
    values: frozenset[ItemStateKeyValue]
    in_world: bool

    def __post_init__(self) -> None:
        keys = [key_value.key for key_value in self.values]
        if len(set(keys)) != len(keys):
            raise RepeatedMementoKeyException(f"{self.item_id.value} has a state key with two values")


class Item(AggregateRoot[ItemEvent]):
    def __init__(
        self,
        item_id: ItemInstanceId,
        spec: ItemSpecDeclaration,
        came_at: WorldTick,
        *,
        values: frozenset[ItemStateKeyValue],
        in_world: bool,
    ) -> None:
        super().__init__()
        self._values = {key_value.key: key_value.value for key_value in values}
        if len(self._values) != len(values):
            raise RepeatedMementoKeyException(f"{item_id.value} has a state key with two values")
        _require_matches(spec, self._values, item_id)
        self._item_id = item_id
        self._spec = spec
        self._came_at = came_at
        self._in_world = in_world

    @classmethod
    def come_into_world(cls, item_id: ItemInstanceId, spec: ItemSpecDeclaration, now: WorldTick) -> Item:
        initial = frozenset(ItemStateKeyValue(state_key.key, state_key.initial) for state_key in spec.state_keys)
        item = cls(item_id, spec, now, values=initial, in_world=True)
        item.add_event(
            ItemCameIntoWorldEvent(**new_event_stamp(), item=item_id, spec_id=spec.item_spec_id, came_at=now)
        )
        return item

    @classmethod
    def from_memento(cls, memento: ItemMemento, design: WorldDesign) -> Item:
        return cls(
            memento.item_id,
            design.nouns.item_spec_of(memento.spec_id),
            memento.came_at,
            values=memento.values,
            in_world=memento.in_world,
        )

    @property
    def item_id(self) -> ItemInstanceId:
        return self._item_id

    @property
    def spec_id(self) -> ItemSpecId:
        return self._spec.item_spec_id

    def memento(self) -> ItemMemento:
        return ItemMemento(
            item_id=self._item_id,
            spec_id=self.spec_id,
            came_at=self._came_at,
            values=frozenset(ItemStateKeyValue(key, value) for key, value in self._values.items()),
            in_world=self._in_world,
        )

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
        self._spec.lasts.require_run_out(self.age(now))
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


def _require_matches(spec: ItemSpecDeclaration, values: dict[StateKeyId, StateValue], item: ItemInstanceId) -> None:
    if {state_key.key for state_key in spec.state_keys} != values.keys():
        raise MementoDoesNotMatchDesignException(
            f"{item.value} has state keys {sorted(key.value for key in values)}, "
            f"but {spec.item_spec_id.value} declares {sorted(state_key.key.value for state_key in spec.state_keys)}"
        )
    for state_key in spec.state_keys:
        if not state_key.kind.can_hold(values[state_key.key]):
            raise StateValueMismatchesKindException(
                f"{values[state_key.key]!r} of {item.value} does not fit {state_key.kind!r} of {state_key.key.value}"
            )
