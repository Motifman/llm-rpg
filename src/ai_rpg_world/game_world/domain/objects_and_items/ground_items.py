from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.eventing import new_event_stamp
from ai_rpg_world.eventing.aggregate_root import AggregateRoot
from ai_rpg_world.eventing.domain_event import DomainEvent
from ai_rpg_world.game_world.domain.exception.game_world_exception import require_distinct_memento_keys
from ai_rpg_world.game_world.domain.exception.objects_and_items_exception import (
    GroundItemAlreadyPlacedException,
    GroundItemNotFoundException,
)
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.value_object import SpotId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign


@final
@dataclass(frozen=True, kw_only=True)
class GroundItemPlacedEvent(DomainEvent):
    spot_id: SpotId
    item: ItemInstanceId


@final
@dataclass(frozen=True, kw_only=True)
class GroundItemTakenEvent(DomainEvent):
    spot_id: SpotId
    item: ItemInstanceId


GroundItemsEvent = GroundItemPlacedEvent | GroundItemTakenEvent


@final
@dataclass(frozen=True)
class GroundItemsMemento:
    spot_id: SpotId
    items: tuple[ItemInstanceId, ...]

    def __post_init__(self) -> None:
        require_distinct_memento_keys(self.items, f"an item lies twice on the ground at {self.spot_id.value}")


class GroundItems(AggregateRoot[GroundItemsEvent]):
    def __init__(self, spot_id: SpotId, *, items: tuple[ItemInstanceId, ...]) -> None:
        super().__init__()
        if len(set(items)) != len(items):
            raise GroundItemAlreadyPlacedException(f"an item lies twice on the ground at {spot_id.value}")
        self._spot_id = spot_id
        self._items = list(items)

    @classmethod
    def start(cls, spot_id: SpotId) -> GroundItems:
        return cls(spot_id, items=())

    @classmethod
    def from_memento(cls, memento: GroundItemsMemento, design: WorldDesign) -> GroundItems:
        return cls(memento.spot_id, items=memento.items)

    @property
    def spot_id(self) -> SpotId:
        return self._spot_id

    def memento(self) -> GroundItemsMemento:
        return GroundItemsMemento(spot_id=self._spot_id, items=tuple(self._items))

    def place(self, item: ItemInstanceId) -> None:
        if item in self._items:
            raise GroundItemAlreadyPlacedException(f"{item.value} is already on the ground at {self._spot_id.value}")
        self._items.append(item)
        self.add_event(GroundItemPlacedEvent(**new_event_stamp(), spot_id=self._spot_id, item=item))

    def take(self, item: ItemInstanceId) -> None:
        if item not in self._items:
            raise GroundItemNotFoundException(f"{item.value} is not on the ground at {self._spot_id.value}")
        self._items.remove(item)
        self.add_event(GroundItemTakenEvent(**new_event_stamp(), spot_id=self._spot_id, item=item))

    def items(self) -> tuple[ItemInstanceId, ...]:
        return tuple(self._items)

    def contains(self, item: ItemInstanceId) -> bool:
        return item in self._items
