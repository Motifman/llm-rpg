from typing import Optional
from dataclasses import dataclass

from src.domain.trade.value_object.trade_id import TradeId
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.value_object.item_instance_id import ItemInstanceId
from src.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType


@dataclass
class GlobalMarketListingReadModel:
    """グローバル取引所画面用ReadModel

    グローバル取引所での出品表示に必要な情報を保持する。
    CQRSパターンのReadModelとして機能する。
    """

    # 取引基本情報
    trade_id: TradeId
    item_spec_id: ItemSpecId
    item_instance_id: ItemInstanceId

    # アイテム表示情報
    item_name: str
    item_quantity: int
    item_type: ItemType
    item_rarity: Rarity

    # 耐久度情報（オプション）
    durability_current: Optional[int]
    durability_max: Optional[int]

    # 価格情報
    requested_gold: int

    @classmethod
    def create_from_trade_data(
        cls,
        trade_id: TradeId,
        item_spec_id: ItemSpecId,
        item_instance_id: ItemInstanceId,
        item_name: str,
        item_quantity: int,
        item_type: ItemType,
        item_rarity: Rarity,
        durability_current: Optional[int],
        durability_max: Optional[int],
        requested_gold: int
    ) -> "GlobalMarketListingReadModel":
        """取引情報からReadModelを作成"""
        return cls(
            trade_id=trade_id,
            item_spec_id=item_spec_id,
            item_instance_id=item_instance_id,
            item_name=item_name,
            item_quantity=item_quantity,
            item_type=item_type,
            item_rarity=item_rarity,
            durability_current=durability_current,
            durability_max=durability_max,
            requested_gold=requested_gold
        )

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
        return self.item_type == ItemType.EQUIPMENT
