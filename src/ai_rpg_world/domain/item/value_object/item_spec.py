from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType
from ai_rpg_world.domain.item.exception import ItemSpecValidationException


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
    equipment_type: Optional[EquipmentType] = None

    def __post_init__(self):
        """バリデーションは__post_init__で実行"""
        if not self.name.strip():
            raise ItemSpecValidationException(f"Item spec: name must not be empty, got '{self.name}'")
        if not self.description.strip():
            raise ItemSpecValidationException(f"Item spec: description must not be empty, got '{self.description}'")
        if self.durability_max is not None and self.durability_max <= 0:
            raise ItemSpecValidationException(f"Item spec: durability_max must be positive, got {self.durability_max}")
        # 耐久度が存在する場合、max_stack_sizeは1でなければならない
        if self.durability_max is not None and self.max_stack_size.value != 1:
            raise ItemSpecValidationException(f"Item spec: items with durability must have max_stack_size of 1, got {self.max_stack_size.value}")
        # 装備タイプのバリデーション
        if self.item_type == ItemType.EQUIPMENT:
            if self.equipment_type is None:
                raise ItemSpecValidationException(f"Item spec: equipment items must have equipment_type, got None")
        else:
            if self.equipment_type is not None:
                raise ItemSpecValidationException(f"Item spec: non-equipment items must not have equipment_type, got {self.equipment_type}")

    def can_create_durability(self) -> bool:
        """耐久度を作成可能かどうか"""
        return self.durability_max is not None

    def is_equipment(self) -> bool:
        """装備品かどうか"""
        return self.item_type == ItemType.EQUIPMENT

    def get_equipment_type(self) -> Optional[EquipmentType]:
        """装備タイプを取得（装備品でない場合はNone）"""
        return self.equipment_type

    def __eq__(self, other: object) -> bool:
        """等価性比較（スペックが同じかどうか）"""
        if not isinstance(other, ItemSpec):
            return NotImplemented
        return self.item_spec_id == other.item_spec_id

    def __hash__(self) -> int:
        """ハッシュ値"""
        return hash(self.item_spec_id)
