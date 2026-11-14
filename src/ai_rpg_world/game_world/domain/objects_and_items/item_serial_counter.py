from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.object_and_item import ItemSpecDeclaration
from ai_rpg_world.game_world.domain.objects_and_items.item import Item
from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.value_object import WorldId, WorldTick
from ai_rpg_world.game_world.domain.value_object._checks import require_int_at_least


@final
@dataclass(frozen=True)
class ItemSerialCounterMemento:
    world_id: WorldId
    issued: int

    def __post_init__(self) -> None:
        require_int_at_least("ItemSerialCounterMemento.issued", self.issued, 0)


@final
class ItemSerialCounter:
    def __init__(self, world_id: WorldId, issued: int) -> None:
        self._world_id = world_id
        self._issued = issued

    @classmethod
    def start(cls, world_id: WorldId) -> ItemSerialCounter:
        return cls(world_id, 0)

    @classmethod
    def from_memento(cls, memento: ItemSerialCounterMemento) -> ItemSerialCounter:
        return cls(memento.world_id, memento.issued)

    @property
    def world_id(self) -> WorldId:
        return self._world_id

    def memento(self) -> ItemSerialCounterMemento:
        return ItemSerialCounterMemento(world_id=self._world_id, issued=self._issued)

    def bring_item_into_world(self, spec: ItemSpecDeclaration, now: WorldTick) -> Item:
        self._issued += 1
        return Item.come_into_world(ItemInstanceId(f"item_{self._issued}"), spec, now)
