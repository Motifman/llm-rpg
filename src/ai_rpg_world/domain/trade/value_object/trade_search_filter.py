from dataclasses import dataclass

from ai_rpg_world.domain.item.enum.item_enum import EquipmentType, ItemType, Rarity
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus
from ai_rpg_world.domain.trade.exception.trade_exception import TradeSearchFilterValidationException


@dataclass(frozen=True)
class TradeSearchFilter:
    """取引検索フィルタ（ドメインValue Object）"""

    # アイテム検索条件
    item_name: str | None = None
    item_types: list[ItemType] | None = None
    rarities: list[Rarity] | None = None
    equipment_types: list[EquipmentType] | None = None

    # 価格範囲フィルタ
    min_price: int | None = None
    max_price: int | None = None

    # 取引ステータスフィルタ
    statuses: list[TradeStatus] | None = None

    def __post_init__(self) -> None:
        """ドメインバリデーション"""
        if self.min_price is not None and self.min_price < 0:
            raise TradeSearchFilterValidationException("Minimum price cannot be negative")
        if self.max_price is not None and self.max_price < 0:
            raise TradeSearchFilterValidationException("Maximum price cannot be negative")
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise TradeSearchFilterValidationException("Minimum price cannot be greater than maximum price")

    @classmethod
    def active_only(cls) -> "TradeSearchFilter":
        """アクティブ取引のみのフィルタを作成"""
        return cls(statuses=[TradeStatus.ACTIVE])

    @classmethod
    def by_item_name(cls, name: str) -> "TradeSearchFilter":
        """アイテム名検索フィルタを作成"""
        return cls(item_name=name)

    @classmethod
    def by_price_range(cls, min_price: int | None = None, max_price: int | None = None) -> "TradeSearchFilter":
        """価格範囲フィルタを作成"""
        return cls(min_price=min_price, max_price=max_price)

    @classmethod
    def by_item_types(cls, item_types: list[ItemType]) -> "TradeSearchFilter":
        """アイテムタイプフィルタを作成"""
        return cls(item_types=item_types)

    @classmethod
    def from_primitives(
        cls,
        item_name: str | None = None,
        item_types: list[str] | None = None,
        rarities: list[str] | None = None,
        equipment_types: list[str] | None = None,
        min_price: int | None = None,
        max_price: int | None = None,
        statuses: list[str] | None = None,
    ) -> "TradeSearchFilter":
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
            statuses=converted_statuses,
        )
