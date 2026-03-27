"""ショップ出品 ReadModel 投影用スナップショット（イベントに付与する）。"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.item.entity.item_instance import ItemInstance


@dataclass(frozen=True)
class ShopListingProjection:
    """出品行の表示に必要な情報（非同期投影で Item リポジトリを読まないため）。"""

    item_name: str
    item_spec_id: int
    quantity: int

    @classmethod
    def from_item(cls, item: ItemInstance) -> ShopListingProjection:
        return cls(
            item_name=item.item_spec.name,
            item_spec_id=item.item_spec.item_spec_id.value,
            quantity=item.quantity,
        )
