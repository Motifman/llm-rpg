from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from domain.item.item import Item


@dataclass
class UniqueItem:
    """ユニークアイテムの実体（耐久度や個体差などの可変情報）

    DBの`item_unique`テーブルに概ね対応する概念。
    - `id` はユニーク行のPKを想定
    - `item` は参照する基本アイテム
    - `durability`, `attack`, `defense` は将来のスキーマに準拠
    """

    id: int
    item: Item
    durability: int
    attack: Optional[int] = None
    defense: Optional[int] = None
    speed: Optional[int] = None

    def __post_init__(self):
        assert self.id >= 0, "unique id must be >= 0"
        assert self.durability >= 0, "durability must be >= 0"
        if self.attack is not None:
            assert self.attack >= 0, "attack must be >= 0"
        if self.defense is not None:
            assert self.defense >= 0, "defense must be >= 0"
        if self.speed is not None:
            assert self.speed >= 0, "speed must be >= 0"

    def is_broken(self) -> bool:
        return self.durability <= 0

    def can_be_traded(self) -> bool:
        """破損していない場合のみ取引可能とする既定動作"""
        return not self.is_broken()

    def use_durability(self, amount: int = 1) -> bool:
        """耐久度を消費し、破損した場合はTrueを返す"""
        self.durability = max(0, self.durability - amount)
        return self.is_broken()

    def repair(self, amount: Optional[int] = None) -> int:
        """耐久度を回復し、実際に回復した量を返す。
        最大値はアイテム個体では持たず、カタログ定義や装備システムの責務とする。
        """
        old = self.durability
        if amount is None:
            # 最大までの回復量が不明なため、ここでは何もしない（0回復）
            return 0
        self.durability = max(0, self.durability + amount)
        return self.durability - old


