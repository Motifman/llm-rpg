from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId


@dataclass(frozen=True)
class GroundItem:
    item_instance_id: ItemInstanceId
    item_spec_id: ItemSpecId
