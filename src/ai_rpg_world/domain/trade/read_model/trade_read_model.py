from datetime import datetime
from typing import Optional
from dataclasses import dataclass

from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType
from ai_rpg_world.domain.trade.value_object.trade_requested_gold import TradeRequestedGold
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus


@dataclass
class TradeReadModel:
    """取引表示用ReadModel

    取引情報を非正規化して保持し、高速なクエリを実現する。
    CQRSパターンのReadModelとして機能する。
    """

    # 取引基本情報
    trade_id: int
    seller_id: int
    seller_name: str
    buyer_id: Optional[int]
    buyer_name: Optional[str]
    requested_gold: int
    status: str
    created_at: datetime

    # アイテム情報（非正規化）
    item_instance_id: int
    item_name: str
    item_quantity: int
    item_type: str  # ItemType enum value
    item_rarity: str  # Rarity enum value
    item_description: str
    item_equipment_type: Optional[str]  # EquipmentType enum value

    # 耐久度情報（オプション）
    durability_current: Optional[int]
    durability_max: Optional[int]

    @classmethod
    def create_from_trade_and_item(
        cls,
        trade_id: TradeId,
        seller_id: PlayerId,
        seller_name: str,
        buyer_id: Optional[PlayerId],
        buyer_name: Optional[str],
        item_instance_id: ItemInstanceId,
        item_name: str,
        item_quantity: int,
        item_type: ItemType,
        item_rarity: Rarity,
        item_description: str,
        item_equipment_type: Optional[EquipmentType],
        durability_current: Optional[int],
        durability_max: Optional[int],
        requested_gold: TradeRequestedGold,
        status: TradeStatus,
        created_at: datetime
    ) -> "TradeReadModel":
        """取引情報とアイテム情報からReadModelを作成"""
        return cls(
            trade_id=int(trade_id),
            seller_id=int(seller_id),
            seller_name=seller_name,
            buyer_id=int(buyer_id) if buyer_id else None,
            buyer_name=buyer_name,
            item_instance_id=int(item_instance_id),
            item_name=item_name,
            item_quantity=item_quantity,
            item_type=item_type.value,
            item_rarity=item_rarity.value,
            item_description=item_description,
            item_equipment_type=item_equipment_type.value if item_equipment_type else None,
            durability_current=durability_current,
            durability_max=durability_max,
            requested_gold=int(requested_gold),
            status=status.name,
            created_at=created_at
        )

    @property
    def is_active(self) -> bool:
        """取引がアクティブかどうか"""
        return self.status == "ACTIVE"

    @property
    def is_completed(self) -> bool:
        """取引が成立済みかどうか"""
        return self.status == "COMPLETED"

    @property
    def has_durability(self) -> bool:
        """耐久度を持つアイテムかどうか"""
        return self.durability_max is not None

    @property
    def durability_percentage(self) -> Optional[float]:
        """耐久度の割合（0.0-1.0）"""
        if not self.has_durability or self.durability_max == 0:
            return None
        return self.durability_current / self.durability_max if self.durability_current else 0.0

    @property
    def is_equipment(self) -> bool:
        """装備品かどうか"""
        return self.item_type == "EQUIPMENT"
