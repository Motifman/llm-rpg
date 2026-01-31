from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING, Dict
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.enum.equipment_slot_type import EquipmentSlotType
from ai_rpg_world.domain.player.enum.inventory_sort_type import InventorySortType

if TYPE_CHECKING:
    from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate


@dataclass(frozen=True)
class ItemAddedToInventoryEvent(BaseDomainEvent[PlayerId, "PlayerInventoryAggregate"]):
    """インベントリにアイテムが追加されたイベント"""
    item_instance_id: ItemInstanceId


@dataclass(frozen=True)
class ItemRemovedFromInventoryEvent(BaseDomainEvent[PlayerId, "PlayerInventoryAggregate"]):
    """インベントリからアイテムが削除されたイベント"""
    item_instance_id: ItemInstanceId


@dataclass(frozen=True)
class ItemDroppedFromInventoryEvent(BaseDomainEvent[PlayerId, "PlayerInventoryAggregate"]):
    """インベントリからアイテムが捨てられたイベント"""
    item_instance_id: ItemInstanceId
    slot_id: SlotId


@dataclass(frozen=True)
class ItemEquippedEvent(BaseDomainEvent[PlayerId, "PlayerInventoryAggregate"]):
    """アイテムが装備されたイベント"""
    item_instance_id: ItemInstanceId
    from_slot_id: SlotId
    to_equipment_slot: EquipmentSlotType


@dataclass(frozen=True)
class ItemUnequippedEvent(BaseDomainEvent[PlayerId, "PlayerInventoryAggregate"]):
    """アイテムが装備解除されたイベント"""
    item_instance_id: ItemInstanceId
    from_equipment_slot: EquipmentSlotType
    to_slot_id: Optional[SlotId] = None  # Noneの場合はドロップ


@dataclass(frozen=True)
class ItemEquipRequestedEvent(BaseDomainEvent[PlayerId, "PlayerInventoryAggregate"]):
    """アイテム装備要求イベント"""
    inventory_slot_id: SlotId
    item_instance_id: ItemInstanceId
    target_equipment_slot: EquipmentSlotType


@dataclass(frozen=True)
class InventorySlotOverflowEvent(BaseDomainEvent[PlayerId, "PlayerInventoryAggregate"]):
    """インベントリスロットが溢れたイベント"""
    overflowed_item_instance_id: ItemInstanceId
    reason: str  # "equip_replacement", "unequip_no_space" など


@dataclass(frozen=True)
class InventoryCompactionRequestedEvent(BaseDomainEvent[PlayerId, "PlayerInventoryAggregate"]):
    """インベントリ整理要求イベント"""


@dataclass(frozen=True)
class InventoryCompactionCompletedEvent(BaseDomainEvent[PlayerId, "PlayerInventoryAggregate"]):
    """インベントリ整理完了イベント"""
    compacted_slots: Dict[SlotId, Optional[ItemInstanceId]]  # slot_id -> item_instance_id


@dataclass(frozen=True)
class InventorySortRequestedEvent(BaseDomainEvent[PlayerId, "PlayerInventoryAggregate"]):
    """インベントリソート要求イベント"""
    sort_criteria: InventorySortType


@dataclass(frozen=True)
class ItemReservedForTradeEvent(BaseDomainEvent[PlayerId, "PlayerInventoryAggregate"]):
    """アイテムが取引のために予約されたイベント"""
    item_instance_id: ItemInstanceId


@dataclass(frozen=True)
class ItemReservationCancelledEvent(BaseDomainEvent[PlayerId, "PlayerInventoryAggregate"]):
    """アイテムの予約がキャンセルされたイベント"""
    item_instance_id: ItemInstanceId
