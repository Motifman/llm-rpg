from dataclasses import dataclass
from typing import Optional
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.value_object.max_stack_size import MaxStackSize
from src.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType


@dataclass
class ItemSpecReadModel:
    """ItemSpec用ReadModel

    CQRSパターンのReadModelとして機能し、ItemSpecの情報を保持する。
    """

    # 識別子
    item_spec_id: ItemSpecId

    # 基本情報
    name: str
    item_type: ItemType
    rarity: Rarity
    description: str
    max_stack_size: MaxStackSize
    durability_max: Optional[int] = None
    equipment_type: Optional[EquipmentType] = None

    @classmethod
    def create_from_item_spec(
        cls,
        item_spec_id: ItemSpecId,
        name: str,
        item_type: ItemType,
        rarity: Rarity,
        description: str,
        max_stack_size: MaxStackSize,
        durability_max: Optional[int] = None,
        equipment_type: Optional[EquipmentType] = None
    ) -> "ItemSpecReadModel":
        """ItemSpecからReadModelを作成"""
        return cls(
            item_spec_id=item_spec_id,
            name=name,
            item_type=item_type,
            rarity=rarity,
            description=description,
            max_stack_size=max_stack_size,
            durability_max=durability_max,
            equipment_type=equipment_type
        )

    @property
    def is_equipment(self) -> bool:
        """装備品かどうか"""
        return self.item_type == ItemType.EQUIPMENT

    @property
    def can_have_durability(self) -> bool:
        """耐久度を持つことができるかどうか"""
        return self.durability_max is not None
