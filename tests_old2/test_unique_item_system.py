import pytest
from game.item.item import Item, StackableItem, UniqueItem
from game.item.consumable_item import ConsumableItem
from game.item.equipment_item import Weapon, Armor, WeaponEffect, ArmorEffect
from game.item.item_effect import ItemEffect
from game.enums import Element, Race, StatusEffectType, DamageType, WeaponType, ArmorType
from game.player.inventory import Inventory


class TestStackableItem:
    def test_stackable_item_creation(self):
        """StackableItemの作成テスト"""
        item = ConsumableItem(
            item_id="test_potion",
            name="テストポーション",
            description="テスト用のポーション",
            effect=ItemEffect(hp_change=10),
            max_stack=5
        )
        
        assert item.item_id == "test_potion"
        assert item.name == "テストポーション"
        assert item.description == "テスト用のポーション"
        assert item.max_stack == 5
        assert isinstance(item, StackableItem)
        assert isinstance(item, Item)
    
    def test_stackable_item_can_stack_with(self):
        """スタック可能アイテムのスタック判定テスト"""
        item1 = ConsumableItem(
            item_id="test_potion",
            name="テストポーション",
            description="テスト用のポーション",
            effect=ItemEffect(hp_change=10),
            max_stack=5
        )
        
        item2 = ConsumableItem(
            item_id="test_potion",
            name="テストポーション",
            description="テスト用のポーション",
            effect=ItemEffect(hp_change=10),
            max_stack=5
        )
        
        item3 = ConsumableItem(
            item_id="test_potion",
            name="テストポーション",
            description="テスト用のポーション",
            effect=ItemEffect(hp_change=10),
            max_stack=3  # 異なるmax_stack
        )
        
        assert item1.can_stack_with(item2)
        assert not item1.can_stack_with(item3)


class TestUniqueItem:
    def test_unique_item_creation(self):
        """UniqueItemの作成テスト"""
        weapon_effect = WeaponEffect(attack_bonus=10)
        weapon = Weapon(
            item_id="test_sword",
            name="テストソード",
            description="テスト用の剣",
            weapon_type=WeaponType.SWORD,
            effect=weapon_effect,
            max_durability=100
        )
        
        assert weapon.item_id == "test_sword"
        assert weapon.name == "テストソード"
        assert weapon.description == "テスト用の剣"
        assert weapon.max_durability == 100
        assert weapon.current_durability == 100
        assert isinstance(weapon, UniqueItem)
        assert isinstance(weapon, Item)
        assert weapon.get_unique_id() is not None
    
    def test_unique_item_unique_id(self):
        """固有IDの一意性テスト"""
        weapon_effect = WeaponEffect(attack_bonus=10)
        weapon1 = Weapon(
            item_id="test_sword",
            name="テストソード",
            description="テスト用の剣",
            weapon_type=WeaponType.SWORD,
            effect=weapon_effect
        )
        
        weapon2 = Weapon(
            item_id="test_sword",
            name="テストソード",
            description="テスト用の剣",
            weapon_type=WeaponType.SWORD,
            effect=weapon_effect
        )
        
        # 同じitem_idでも異なるunique_idを持つ
        assert weapon1.item_id == weapon2.item_id
        assert weapon1.get_unique_id() != weapon2.get_unique_id()
    
    def test_weapon_durability_system(self):
        """武器の耐久度システムテスト"""
        weapon_effect = WeaponEffect(attack_bonus=10)
        weapon = Weapon(
            item_id="test_sword",
            name="テストソード",
            description="テスト用の剣",
            weapon_type=WeaponType.SWORD,
            effect=weapon_effect,
            max_durability=100
        )
        
        # 初期状態
        assert weapon.current_durability == 100
        assert not weapon.is_broken()
        
        # 耐久度消費
        is_broken = weapon.use_durability(30)
        assert weapon.current_durability == 70
        assert not is_broken
        assert not weapon.is_broken()
        
        # 耐久度回復
        repaired = weapon.repair(20)
        assert weapon.current_durability == 90
        assert repaired == 20
        
        # 完全回復
        repaired = weapon.repair()
        assert weapon.current_durability == 100
        assert repaired == 10
        
        # 破損テスト
        is_broken = weapon.use_durability(100)
        assert weapon.current_durability == 0
        assert is_broken
        assert weapon.is_broken()
    
    def test_armor_durability_system(self):
        """防具の耐久度システムテスト"""
        armor_effect = ArmorEffect(defense_bonus=5)
        armor = Armor(
            item_id="test_armor",
            name="テストアーマー",
            description="テスト用の防具",
            armor_type=ArmorType.HELMET,
            effect=armor_effect,
            max_durability=80
        )
        
        # 初期状態
        assert armor.current_durability == 80
        assert not armor.is_broken()
        
        # 耐久度消費
        is_broken = armor.use_durability(25)
        assert armor.current_durability == 55
        assert not is_broken
        
        # 耐久度回復
        repaired = armor.repair(15)
        assert armor.current_durability == 70
        assert repaired == 15
    
    def test_get_status_description(self):
        """状態説明のテスト"""
        weapon_effect = WeaponEffect(attack_bonus=10)
        weapon = Weapon(
            item_id="test_sword",
            name="テストソード",
            description="テスト用の剣",
            weapon_type=WeaponType.SWORD,
            effect=weapon_effect,
            max_durability=100
        )
        
        status_desc = weapon.get_status_description()
        assert "sword" in status_desc
        assert "耐久度: 100/100" in status_desc
        assert "(100%)" in status_desc
        
        # 耐久度を消費した後の状態説明
        weapon.use_durability(30)
        status_desc = weapon.get_status_description()
        assert "耐久度: 70/100" in status_desc
        assert "(70%)" in status_desc


class TestInventoryWithNewStructure:
    def test_inventory_with_stackable_and_unique_items(self):
        """新しい構造でのインベントリテスト"""
        inventory = Inventory()
        
        # スタック可能アイテム（ConsumableItem）
        potion = ConsumableItem(
            item_id="health_potion",
            name="体力ポーション",
            description="体力を回復する",
            effect=ItemEffect(hp_change=20),
            max_stack=10
        )
        
        # 固有アイテム（Weapon）
        weapon_effect = WeaponEffect(attack_bonus=15)
        sword = Weapon(
            item_id="iron_sword",
            name="鉄の剣",
            description="鉄で作られた剣",
            weapon_type=WeaponType.SWORD,
            effect=weapon_effect,
            max_durability=100
        )
        
        # アイテムを追加
        inventory.add_item(potion)
        inventory.add_item(potion)  # スタック
        inventory.add_item(sword)
        
        # 確認
        assert inventory.get_item_count("health_potion") == 2
        assert inventory.get_item_count("iron_sword") == 1
        assert inventory.has_item("health_potion")
        assert inventory.has_item("iron_sword")
        
        # 固有アイテムの取得
        retrieved_sword = inventory.get_item_by_id("iron_sword", sword.get_unique_id())
        assert retrieved_sword is not None
        assert retrieved_sword.get_unique_id() == sword.get_unique_id()
    
    def test_inventory_remove_unique_item(self):
        """固有アイテムの削除テスト"""
        inventory = Inventory()
        
        weapon_effect = WeaponEffect(attack_bonus=15)
        sword = Weapon(
            item_id="iron_sword",
            name="鉄の剣",
            description="鉄で作られた剣",
            weapon_type=WeaponType.SWORD,
            effect=weapon_effect
        )
        
        inventory.add_item(sword)
        assert inventory.has_item("iron_sword")
        
        # unique_idを指定して削除
        removed = inventory.remove_item_by_id("iron_sword", 1, sword.get_unique_id())
        assert removed == 1
        assert not inventory.has_item("iron_sword")
    
    def test_inventory_display_with_new_structure(self):
        """新しい構造でのインベントリ表示テスト"""
        inventory = Inventory()
        
        # スタック可能アイテム
        potion = ConsumableItem(
            item_id="health_potion",
            name="体力ポーション",
            description="体力を回復する",
            effect=ItemEffect(hp_change=20),
            max_stack=10
        )
        
        # 固有アイテム
        weapon_effect = WeaponEffect(attack_bonus=15)
        sword = Weapon(
            item_id="iron_sword",
            name="鉄の剣",
            description="鉄で作られた剣",
            weapon_type=WeaponType.SWORD,
            effect=weapon_effect,
            max_durability=100
        )
        
        inventory.add_item(potion)
        inventory.add_item(potion)
        inventory.add_item(sword)
        
        display = inventory.get_inventory_display()
        
        # スタック可能アイテムの表示確認
        assert "health_potion x2" in display
        assert "体力を回復する" in display
        
        # 固有アイテムの表示確認（get_status_description()が使用される）
        assert "sword - 耐久度: 100/100" in display
        assert "鉄で作られた剣" in display


class TestBackwardCompatibility:
    def test_old_item_compatibility(self):
        """既存のItemクラスとの後方互換性テスト"""
        inventory = Inventory()
        
        # 古いItemクラスを使用
        old_item = Item(
            item_id="old_item",
            name="古いアイテム",
            description="後方互換性テスト用"
        )
        
        inventory.add_item(old_item)
        assert inventory.has_item("old_item")
        assert inventory.get_item_count("old_item") == 1
        
        # 削除も正常に動作
        removed = inventory.remove_item_by_id("old_item", 1)
        assert removed == 1
        assert not inventory.has_item("old_item") 