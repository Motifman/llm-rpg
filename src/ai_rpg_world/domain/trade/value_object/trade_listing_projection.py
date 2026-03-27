from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.item.entity.item_instance import ItemInstance
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType


@dataclass(frozen=True)
class TradeListingProjection:
    """取引 ReadModel 投影用の出品表示スナップショット（イベントに付与する）。

    コマンド実行時点の表示情報のみを保持し、非同期投影で別リポジトリを読まないために使う。
    """

    seller_display_name: str
    item_name: str
    item_quantity: int
    item_type: ItemType
    item_rarity: Rarity
    item_description: str
    item_equipment_type: Optional[EquipmentType]
    durability_current: Optional[int]
    durability_max: Optional[int]

    @classmethod
    def from_seller_and_item(
        cls,
        seller_display_name: str,
        item: ItemInstance,
    ) -> TradeListingProjection:
        spec = item.item_spec
        durability = item.durability
        return cls(
            seller_display_name=seller_display_name,
            item_name=spec.name,
            item_quantity=item.quantity,
            item_type=spec.item_type,
            item_rarity=spec.rarity,
            item_description=spec.description,
            item_equipment_type=spec.equipment_type,
            durability_current=durability.current if durability else None,
            durability_max=durability.max_value if durability else None,
        )
