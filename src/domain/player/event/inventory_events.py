from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING
from src.domain.common.domain_event import BaseDomainEvent
from src.domain.player.value_object.player_inventory_id import PlayerInventoryId

if TYPE_CHECKING:
    from src.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate


@dataclass(frozen=True)
class ItemAddedToInventoryEvent(BaseDomainEvent[PlayerInventoryId, "PlayerInventoryAggregate"]):
    """インベントリにアイテムが追加されたイベント"""
    player_id: int
    item_id: int
    quantity: Optional[int] = None
    unique_id: Optional[int] = None


@dataclass(frozen=True)
class ItemRemovedFromInventoryEvent(BaseDomainEvent[PlayerInventoryId, "PlayerInventoryAggregate"]):
    """インベントリからアイテムが削除されたイベント"""
    player_id: int
    item_id: int
    quantity: Optional[int] = None
    unique_id: Optional[int] = None
