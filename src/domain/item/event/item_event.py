from dataclasses import dataclass
from typing import Optional
from src.domain.common.domain_event import BaseDomainEvent
from src.domain.item.value_object.item_instance_id import ItemInstanceId
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.value_object.durability import Durability
from src.domain.item.value_object.recipe_id import RecipeId


@dataclass(frozen=True)
class ItemUsedEvent(BaseDomainEvent[ItemInstanceId, "ItemAggregate"]):
    """アイテム使用イベント"""
    item_instance_id: ItemInstanceId
    item_spec_id: ItemSpecId
    remaining_quantity: int
    remaining_durability: Optional[Durability]


@dataclass(frozen=True)
class ItemBrokenEvent(BaseDomainEvent[ItemInstanceId, "ItemAggregate"]):
    """アイテム破損イベント"""
    item_instance_id: ItemInstanceId
    item_spec_id: ItemSpecId


@dataclass(frozen=True)
class ItemRepairedEvent(BaseDomainEvent[ItemInstanceId, "ItemAggregate"]):
    """アイテム修理イベント"""
    item_instance_id: ItemInstanceId
    item_spec_id: ItemSpecId
    new_durability: Optional[Durability]


@dataclass(frozen=True)
class ItemCraftedEvent(BaseDomainEvent[ItemInstanceId, "ItemAggregate"]):
    """アイテム合成イベント"""
    item_instance_id: ItemInstanceId
    item_spec_id: ItemSpecId
    quantity: int
