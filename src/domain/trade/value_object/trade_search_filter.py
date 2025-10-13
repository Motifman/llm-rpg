from dataclasses import dataclass
from typing import Optional, List
from src.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType
from src.domain.trade.enum.trade_enum import TradeStatus
from src.domain.trade.exception.trade_exception import TradeSearchFilterValidationException


@dataclass(frozen=True)
class TradeSearchFilter:
    """取引検索フィルタ（ドメインValue Object）"""

    # アイテム検索条件
    item_name: Optional[str] = None
    item_types: Optional[List[ItemType]] = None
    rarities: Optional[List[Rarity]] = None
    equipment_types: Optional[List[EquipmentType]] = None

    # 価格範囲フィルタ
    min_price: Optional[int] = None
    max_price: Optional[int] = None

    # 取引ステータスフィルタ
    statuses: Optional[List[TradeStatus]] = None

    def __post_init__(self):
        """ドメインバリデーション"""
        if self.min_price is not None and self.min_price < 0:
            raise TradeSearchFilterValidationException("Minimum price cannot be negative")
        if self.max_price is not None and self.max_price < 0:
            raise TradeSearchFilterValidationException("Maximum price cannot be negative")
        if (self.min_price is not None and self.max_price is not None and
            self.min_price > self.max_price):
            raise TradeSearchFilterValidationException("Minimum price cannot be greater than maximum price")

    @classmethod
    def active_only(cls) -> 'TradeSearchFilter':
        """アクティブ取引のみのフィルタを作成"""
        return cls(statuses=[TradeStatus.ACTIVE])

    @classmethod
    def by_item_name(cls, name: str) -> 'TradeSearchFilter':
        """アイテム名検索フィルタを作成"""
        return cls(item_name=name)

    @classmethod
    def by_price_range(cls, min_price: Optional[int] = None,
                      max_price: Optional[int] = None) -> 'TradeSearchFilter':
        """価格範囲フィルタを作成"""
        return cls(min_price=min_price, max_price=max_price)

    @classmethod
    def by_item_types(cls, item_types: List[ItemType]) -> 'TradeSearchFilter':
        """アイテムタイプフィルタを作成"""
        return cls(item_types=item_types)

    @classmethod
    def from_primitives(
        cls,
        item_name: Optional[str] = None,
        item_types: Optional[List[str]] = None,
        rarities: Optional[List[str]] = None,
        equipment_types: Optional[List[str]] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        statuses: Optional[List[str]] = None
    ) -> 'TradeSearchFilter':
        """プリミティブ型からValue Objectを作成（ファクトリーメソッド）"""
        # enum変換
        converted_item_types = None
        if item_types:
            converted_item_types = [ItemType(t) for t in item_types]

        converted_rarities = None
        if rarities:
            converted_rarities = [Rarity(r) for r in rarities]

        converted_equipment_types = None
        if equipment_types:
            converted_equipment_types = [EquipmentType(et) for et in equipment_types]

        converted_statuses = None
        if statuses:
            converted_statuses = [TradeStatus(s) for s in statuses]

        return cls(
            item_name=item_name,
            item_types=converted_item_types,
            rarities=converted_rarities,
            equipment_types=converted_equipment_types,
            min_price=min_price,
            max_price=max_price,
            statuses=converted_statuses
        )
