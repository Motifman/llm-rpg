from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.objects_and_items.item_instance_id import ItemInstanceId
from ai_rpg_world.game_world.domain.value_object import PersonId


@final
@dataclass(frozen=True)
class Delivery:
    item: ItemInstanceId
    to: PersonId
