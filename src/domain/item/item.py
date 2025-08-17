from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.domain.item.item_enum import ItemType, Rarity
from src.domain.item.item_effect import ItemEffect


@dataclass(frozen=True)
class Item:
    """基本アイテム情報（全アイテム共通の不変情報）

    DBの`item`テーブルに概ね対応する概念。
    - `item_id` は商品カタログ上の識別子（将来的にDBのPKに対応）
    - `type`, `rarity` は列挙により安全に制約
    """

    item_id: int
    name: str
    description: str
    price: int
    item_type: ItemType
    rarity: Rarity
    item_effect: Optional[ItemEffect] = None

    def __post_init__(self):
        if self.price < 0:
            raise ValueError(f"price must be >= 0. price: {self.price}")
        if self.name == "":
            raise ValueError(f"name must not be empty. name: {self.name}")
        if self.description == "":
            raise ValueError(f"description must not be empty. description: {self.description}")
        if self.item_id < 0:
            raise ValueError(f"item_id must be >= 0. item_id: {self.item_id}")
        if self.item_type is None:
            raise ValueError(f"item_type must not be None. item_type: {self.item_type}")
        if self.rarity is None:
            raise ValueError(f"rarity must not be None. rarity: {self.rarity}")

    def can_be_traded(self) -> bool:
        """カタログ上の定義としては取引可能（ユニーク実体の状態により変わる場合は別で判定）"""
        return True


