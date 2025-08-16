from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.domain.item.item_enum import ItemType, Rarity


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
    type: ItemType
    rarity: Rarity

    def __post_init__(self):
        assert self.item_id >= 0, "item_id must be >= 0"
        assert self.price >= 0, "price must be >= 0"
        assert self.name != "", "name must not be empty"
        assert self.description != "", "description must not be empty"

    def can_be_traded(self) -> bool:
        """カタログ上の定義としては取引可能（ユニーク実体の状態により変わる場合は別で判定）"""
        return True


