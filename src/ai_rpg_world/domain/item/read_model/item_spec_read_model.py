from dataclasses import dataclass
from typing import Optional
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType


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
    is_placeable: bool = False
    placeable_object_type: Optional[str] = None

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
        equipment_type: Optional[EquipmentType] = None,
        is_placeable: bool = False,
        placeable_object_type: Optional[str] = None,
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
            equipment_type=equipment_type,
            is_placeable=is_placeable,
            placeable_object_type=placeable_object_type,
        )

    @property
    def is_equipment(self) -> bool:
        """装備品かどうか"""
        return self.item_type == ItemType.EQUIPMENT

    @property
    def can_have_durability(self) -> bool:
        """耐久度を持つことができるかどうか"""
        return self.durability_max is not None

    @property
    def is_placeable_item(self) -> bool:
        """設置可能アイテムかどうか"""
        return self.is_placeable

    def to_item_spec(self) -> "ItemSpec":
        """ItemSpecReadModelをItemSpecに変換"""
        from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
        return ItemSpec(
            item_spec_id=self.item_spec_id,
            name=self.name,
            item_type=self.item_type,
            rarity=self.rarity,
            description=self.description,
            max_stack_size=self.max_stack_size,
            durability_max=self.durability_max,
            equipment_type=self.equipment_type,
            is_placeable=self.is_placeable,
            placeable_object_type=self.placeable_object_type,
        )
