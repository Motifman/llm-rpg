"""
InMemoryItemSpecRepository - ItemSpecを使用するインメモリ実装
"""
from typing import List, Optional, Dict
from src.domain.item.repository.item_spec_repository import ItemSpecRepository
from src.domain.item.value_object.item_spec import ItemSpec
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.value_object.max_stack_size import MaxStackSize
from src.domain.item.enum.item_enum import ItemType, Rarity, EquipmentType


class InMemoryItemSpecRepository(ItemSpecRepository):
    """ItemSpecを使用するインメモリリポジトリ"""

    def __init__(self):
        self._item_specs: Dict[ItemSpecId, ItemSpec] = {}
        self._name_to_item_spec: Dict[str, ItemSpec] = {}
        self._next_item_spec_id = ItemSpecId(1)

        # サンプルアイテムデータをセットアップ
        self._setup_sample_data()

    def _setup_sample_data(self):
        """サンプルアイテムデータのセットアップ"""
        # 装備品系アイテム
        sword_spec = ItemSpec(
            item_spec_id=ItemSpecId(1),
            name="鉄の剣",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.COMMON,
            description="基本的な鉄製の剣。冒険者の定番武器。",
            max_stack_size=MaxStackSize(1),
            durability_max=100,
            equipment_type=EquipmentType.WEAPON
        )
        self._save_item_spec(sword_spec)

        steel_sword_spec = ItemSpec(
            item_spec_id=ItemSpecId(2),
            name="鋼の剣",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.UNCOMMON,
            description="鋭い鋼製の剣。攻撃力が高い。",
            max_stack_size=MaxStackSize(1),
            durability_max=120,
            equipment_type=EquipmentType.WEAPON
        )
        self._save_item_spec(steel_sword_spec)

        legendary_sword_spec = ItemSpec(
            item_spec_id=ItemSpecId(3),
            name="伝説の剣",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.LEGENDARY,
            description="古代の英雄が使っていたという伝説の剣。",
            max_stack_size=MaxStackSize(1),
            durability_max=200,
            equipment_type=EquipmentType.WEAPON
        )
        self._save_item_spec(legendary_sword_spec)

        # 防具系アイテム
        leather_armor_spec = ItemSpec(
            item_spec_id=ItemSpecId(4),
            name="革の鎧",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.COMMON,
            description="軽量な革製の鎧。防御力は低いが動きやすい。",
            max_stack_size=MaxStackSize(1),
            durability_max=80,
            equipment_type=EquipmentType.ARMOR
        )
        self._save_item_spec(leather_armor_spec)

        iron_armor_spec = ItemSpec(
            item_spec_id=ItemSpecId(5),
            name="鉄の鎧",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.UNCOMMON,
            description="頑丈な鉄製の鎧。防御力が高い。",
            max_stack_size=MaxStackSize(1),
            durability_max=150,
            equipment_type=EquipmentType.ARMOR
        )
        self._save_item_spec(iron_armor_spec)

        # 消耗品アイテム
        health_potion_spec = ItemSpec(
            item_spec_id=ItemSpecId(6),
            name="回復ポーション",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            description="HPを50回復する魔法のポーション。",
            max_stack_size=MaxStackSize(99)
        )
        self._save_item_spec(health_potion_spec)

        mana_potion_spec = ItemSpec(
            item_spec_id=ItemSpecId(7),
            name="マナポーション",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.COMMON,
            description="MPを30回復する魔法のポーション。",
            max_stack_size=MaxStackSize(99)
        )
        self._save_item_spec(mana_potion_spec)

        greater_health_potion_spec = ItemSpec(
            item_spec_id=ItemSpecId(8),
            name="上級回復ポーション",
            item_type=ItemType.CONSUMABLE,
            rarity=Rarity.UNCOMMON,
            description="HPを150回復する強力なポーション。",
            max_stack_size=MaxStackSize(50)
        )
        self._save_item_spec(greater_health_potion_spec)

        # 素材アイテム
        iron_ore_spec = ItemSpec(
            item_spec_id=ItemSpecId(9),
            name="鉄鉱石",
            item_type=ItemType.MATERIAL,
            rarity=Rarity.COMMON,
            description="鉄の武器や防具を作るための素材。",
            max_stack_size=MaxStackSize(64)
        )
        self._save_item_spec(iron_ore_spec)

        steel_ingot_spec = ItemSpec(
            item_spec_id=ItemSpecId(10),
            name="鋼鉄インゴット",
            item_type=ItemType.MATERIAL,
            rarity=Rarity.UNCOMMON,
            description="高品質な鋼鉄のインゴット。武器強化に使用。",
            max_stack_size=MaxStackSize(32)
        )
        self._save_item_spec(steel_ingot_spec)

        mystic_crystal_spec = ItemSpec(
            item_spec_id=ItemSpecId(11),
            name="神秘のクリスタル",
            item_type=ItemType.MATERIAL,
            rarity=Rarity.RARE,
            description="魔法の力が宿った希少なクリスタル。",
            max_stack_size=MaxStackSize(16)
        )
        self._save_item_spec(mystic_crystal_spec)

        # クエストアイテム
        ancient_scroll_spec = ItemSpec(
            item_spec_id=ItemSpecId(12),
            name="古代の巻物",
            item_type=ItemType.QUEST,
            rarity=Rarity.EPIC,
            description="古代の魔法が記された貴重な巻物。",
            max_stack_size=MaxStackSize(1)
        )
        self._save_item_spec(ancient_scroll_spec)

        # その他アイテム
        rope_spec = ItemSpec(
            item_spec_id=ItemSpecId(13),
            name="ロープ",
            item_type=ItemType.OTHER,
            rarity=Rarity.COMMON,
            description="丈夫なロープ。様々な場面で役立つ。",
            max_stack_size=MaxStackSize(10)
        )
        self._save_item_spec(rope_spec)

        # 取引不可能なアイテム（クエスト専用）
        quest_key_spec = ItemSpec(
            item_spec_id=ItemSpecId(14),
            name="クエストキー",
            item_type=ItemType.QUEST,
            rarity=Rarity.RARE,
            description="特定のクエストでしか使えない特別な鍵。",
            max_stack_size=MaxStackSize(1)
        )
        self._save_item_spec(quest_key_spec)

        # その他の装備品アイテム
        leather_boots_spec = ItemSpec(
            item_spec_id=ItemSpecId(15),
            name="革の靴",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.COMMON,
            description="軽い革製の靴。歩きやすい。",
            max_stack_size=MaxStackSize(1),
            durability_max=60,
            equipment_type=EquipmentType.BOOTS
        )
        self._save_item_spec(leather_boots_spec)

        leather_gloves_spec = ItemSpec(
            item_spec_id=ItemSpecId(16),
            name="革の手袋",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.COMMON,
            description="基本的な革製の手袋。",
            max_stack_size=MaxStackSize(1),
            durability_max=50,
            equipment_type=EquipmentType.ACCESSORY
        )
        self._save_item_spec(leather_gloves_spec)

        leather_helmet_spec = ItemSpec(
            item_spec_id=ItemSpecId(17),
            name="革の兜",
            item_type=ItemType.EQUIPMENT,
            rarity=Rarity.COMMON,
            description="頭を守る革製の兜。",
            max_stack_size=MaxStackSize(1),
            durability_max=70,
            equipment_type=EquipmentType.HELMET
        )
        self._save_item_spec(leather_helmet_spec)

    def _save_item_spec(self, item_spec: ItemSpec):
        """アイテムスペックを保存（内部用）"""
        self._item_specs[item_spec.item_spec_id] = item_spec
        self._name_to_item_spec[item_spec.name] = item_spec

    def find_by_id(self, item_spec_id: ItemSpecId) -> Optional[ItemSpec]:
        """IDで検索"""
        return self._item_specs.get(item_spec_id)

    def find_by_ids(self, item_spec_ids: List[ItemSpecId]) -> List[ItemSpec]:
        """IDのリストで検索"""
        return [self._item_specs[item_spec_id] for item_spec_id in item_spec_ids if item_spec_id in self._item_specs]

    def find_all(self) -> List[ItemSpec]:
        """全件取得"""
        return list(self._item_specs.values())

    def save(self, item_spec: ItemSpec) -> ItemSpec:
        """保存"""
        self._save_item_spec(item_spec)
        return item_spec

    def delete(self, item_spec_id: ItemSpecId) -> bool:
        """削除"""
        if item_spec_id in self._item_specs:
            item_spec = self._item_specs[item_spec_id]
            del self._item_specs[item_spec_id]
            if item_spec.name in self._name_to_item_spec:
                del self._name_to_item_spec[item_spec.name]
            return True
        return False

    def find_by_type(self, item_type: ItemType) -> List[ItemSpec]:
        """アイテムタイプで検索"""
        return [
            item_spec for item_spec in self._item_specs.values()
            if item_spec.item_type == item_type
        ]

    def find_by_rarity(self, rarity: Rarity) -> List[ItemSpec]:
        """レアリティで検索"""
        return [
            item_spec for item_spec in self._item_specs.values()
            if item_spec.rarity == rarity
        ]

    def find_tradeable_items(self) -> List[ItemSpec]:
        """取引可能なアイテムを検索（クエストアイテム以外）"""
        return [
            item_spec for item_spec in self._item_specs.values()
            if item_spec.item_type != ItemType.QUEST
        ]

    def find_by_name(self, name: str) -> Optional[ItemSpec]:
        """名前で検索"""
        return self._name_to_item_spec.get(name)
