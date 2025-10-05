from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.value_object.max_stack_size import MaxStackSize
from src.domain.item.enum.item_enum import ItemType, Rarity
from src.domain.item.exception import ItemSpecValidationException


@dataclass(frozen=True)
class ItemSpec:
    """アイテム仕様値オブジェクト

    アイテムの同一性を表し、スペックが同じアイテムを識別する。
    """
    item_spec_id: ItemSpecId
    name: str
    item_type: ItemType
    rarity: Rarity
    description: str
    max_stack_size: MaxStackSize
    durability_max: Optional[int] = None

    def __post_init__(self):
        """バリデーションは__post_init__で実行"""
        if not self.name.strip():
            raise ItemSpecValidationException(
                field="name",
                value=self.name,
                reason="name must not be empty"
            )
        if not self.description.strip():
            raise ItemSpecValidationException(
                field="description",
                value=self.description,
                reason="description must not be empty"
            )
        if self.durability_max is not None and self.durability_max <= 0:
            raise ItemSpecValidationException(
                field="durability_max",
                value=self.durability_max,
                reason="durability_max must be positive"
            )

    def can_create_durability(self) -> bool:
        """耐久度を作成可能かどうか"""
        return self.durability_max is not None

    def __eq__(self, other: object) -> bool:
        """等価性比較（スペックが同じかどうか）"""
        if not isinstance(other, ItemSpec):
            return NotImplemented
        return self.item_spec_id == other.item_spec_id

    def __hash__(self) -> int:
        """ハッシュ値"""
        return hash(self.item_spec_id)
