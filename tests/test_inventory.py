#!/usr/bin/env python3
"""
Inventoryクラスの包括的なテスト
"""

import pytest
from game.player.inventory import Inventory
from game.item.item import Item
from game.item.equipment_item import Weapon, Armor, WeaponEffect, ArmorEffect
from game.enums import WeaponType, ArmorType, Element, Race, StatusEffectType, DamageType


class TestInventory:
    """Inventoryクラスのテストクラス"""
    
    def setup_method(self):
        """各テストメソッドの前に実行されるセットアップ"""
        self.inventory = Inventory()
        
        # テスト用アイテムを作成
        self.sword = Item("sword", "鉄の剣", "鉄の剣 - 攻撃力+10")
        self.potion = Item("potion", "回復薬", "回復薬 - HPを50回復")
        self.shield = Item("shield", "木の盾", "木の盾 - 防御力+5")
        self.arrow = Item("arrow", "矢", "矢 - 遠距離攻撃用")
        
        # 装備アイテムを作成
        weapon_effect = WeaponEffect(attack_bonus=15, element=Element.FIRE, element_damage=5)
        self.fire_sword = Weapon("fire_sword", "炎の剣", "炎の剣 - 火属性攻撃", WeaponType.SWORD, weapon_effect)
        
        armor_effect = ArmorEffect(defense_bonus=8, evasion_bonus=0.1)
        self.leather_armor = Armor("leather_armor", "革の鎧", "革の鎧 - 軽量で動きやすい", ArmorType.CHEST, armor_effect)
    
    def test_inventory_initialization(self):
        """インベントリの初期化テスト"""
        assert self.inventory.item_counts == {}
        assert self.inventory.item_references == {}
        assert self.inventory.get_total_item_count() == 0
        assert self.inventory.get_unique_item_count() == 0
    
    def test_add_item_basic(self):
        """基本的なアイテム追加テスト"""
        self.inventory.add_item(self.sword)
        
        assert self.inventory.get_item_count("sword") == 1
        assert self.inventory.has_item("sword") == True
        assert self.inventory.get_total_item_count() == 1
        assert self.inventory.get_unique_item_count() == 1
    
    def test_add_item_duplicate(self):
        """重複アイテムの追加テスト"""
        self.inventory.add_item(self.sword)
        self.inventory.add_item(self.sword)
        self.inventory.add_item(self.sword)
        
        assert self.inventory.get_item_count("sword") == 3
        assert self.inventory.get_total_item_count() == 3
        assert self.inventory.get_unique_item_count() == 1
    
    def test_add_multiple_items(self):
        """複数アイテムの追加テスト"""
        self.inventory.add_item(self.sword)
        self.inventory.add_item(self.potion)
        self.inventory.add_item(self.shield)
        
        assert self.inventory.get_item_count("sword") == 1
        assert self.inventory.get_item_count("potion") == 1
        assert self.inventory.get_item_count("shield") == 1
        assert self.inventory.get_total_item_count() == 3
        assert self.inventory.get_unique_item_count() == 3
    
    def test_remove_item_basic(self):
        """基本的なアイテム削除テスト"""
        self.inventory.add_item(self.sword)
        self.inventory.add_item(self.sword)
        
        removed = self.inventory.remove_item_by_id("sword", 1)
        assert removed == 1
        assert self.inventory.get_item_count("sword") == 1
        assert self.inventory.has_item("sword") == True
    
    def test_remove_item_all(self):
        """アイテムを全て削除するテスト"""
        self.inventory.add_item(self.sword)
        self.inventory.add_item(self.sword)
        
        removed = self.inventory.remove_item_by_id("sword", 2)
        assert removed == 2
        assert self.inventory.get_item_count("sword") == 0
        assert self.inventory.has_item("sword") == False
        assert "sword" not in self.inventory.item_counts
        assert "sword" not in self.inventory.item_references
    
    def test_remove_item_nonexistent(self):
        """存在しないアイテムの削除テスト"""
        removed = self.inventory.remove_item_by_id("nonexistent", 1)
        assert removed == 0
        assert self.inventory.get_item_count("nonexistent") == 0
    
    def test_remove_item_excess(self):
        """所有数より多い数の削除テスト"""
        self.inventory.add_item(self.sword)
        
        removed = self.inventory.remove_item_by_id("sword", 5)
        assert removed == 1
        assert self.inventory.get_item_count("sword") == 0
        assert self.inventory.has_item("sword") == False
    
    def test_remove_item_method(self):
        """remove_itemメソッドのテスト"""
        self.inventory.add_item(self.sword)
        
        self.inventory.remove_item(self.sword)
        assert self.inventory.get_item_count("sword") == 0
        assert self.inventory.has_item("sword") == False
    
    def test_get_item_by_id(self):
        """アイテムIDによるアイテム取得テスト"""
        self.inventory.add_item(self.sword)
        
        item = self.inventory.get_item_by_id("sword")
        assert item is not None
        assert item.item_id == "sword"
        assert item.name == "鉄の剣"
        assert item.description == "鉄の剣 - 攻撃力+10"
    
    def test_get_item_by_id_nonexistent(self):
        """存在しないアイテムIDでの取得テスト"""
        item = self.inventory.get_item_by_id("nonexistent")
        assert item is None
    
    def test_get_items(self):
        """全アイテムリスト取得テスト"""
        self.inventory.add_item(self.sword)
        self.inventory.add_item(self.sword)
        self.inventory.add_item(self.potion)
        
        items = self.inventory.get_items()
        assert len(items) == 3
        
        # アイテムの種類を確認
        sword_count = sum(1 for item in items if item.item_id == "sword")
        potion_count = sum(1 for item in items if item.item_id == "potion")
        assert sword_count == 2
        assert potion_count == 1
    
    def test_get_items_empty(self):
        """空のインベントリでの全アイテム取得テスト"""
        items = self.inventory.get_items()
        assert items == []
    
    def test_has_item(self):
        """アイテム存在確認テスト"""
        self.inventory.add_item(self.sword)
        
        assert self.inventory.has_item("sword") == True
        assert self.inventory.has_item("nonexistent") == False
    
    def test_has_item_after_removal(self):
        """削除後のアイテム存在確認テスト"""
        self.inventory.add_item(self.sword)
        self.inventory.remove_item_by_id("sword", 1)
        
        assert self.inventory.has_item("sword") == False
    
    def test_get_summary(self):
        """インベントリサマリー取得テスト"""
        self.inventory.add_item(self.sword)
        self.inventory.add_item(self.sword)
        self.inventory.add_item(self.potion)
        
        summary = self.inventory.get_summary()
        assert "sword" in summary
        assert "potion" in summary
        assert "(x2)" in summary  # swordの個数
        assert "(x1)" in summary  # potionの個数
    
    def test_get_summary_empty(self):
        """空のインベントリのサマリー取得テスト"""
        summary = self.inventory.get_summary()
        assert summary == ""
    
    def test_get_inventory_display(self):
        """インベントリ表示テスト"""
        self.inventory.add_item(self.sword)
        self.inventory.add_item(self.potion)
        
        display = self.inventory.get_inventory_display()
        assert "=== インベントリ ===" in display
        assert "sword" in display
        assert "potion" in display
        assert "鉄の剣 - 攻撃力+10" in display
        assert "回復薬 - HPを50回復" in display
    
    def test_get_inventory_display_empty(self):
        """空のインベントリの表示テスト"""
        display = self.inventory.get_inventory_display()
        assert display == "インベントリは空です。"
    
    def test_get_total_item_count(self):
        """総アイテム数取得テスト"""
        assert self.inventory.get_total_item_count() == 0
        
        self.inventory.add_item(self.sword)
        assert self.inventory.get_total_item_count() == 1
        
        self.inventory.add_item(self.sword)
        assert self.inventory.get_total_item_count() == 2
        
        self.inventory.add_item(self.potion)
        assert self.inventory.get_total_item_count() == 3
    
    def test_get_unique_item_count(self):
        """ユニークアイテム数取得テスト"""
        assert self.inventory.get_unique_item_count() == 0
        
        self.inventory.add_item(self.sword)
        assert self.inventory.get_unique_item_count() == 1
        
        self.inventory.add_item(self.sword)  # 重複
        assert self.inventory.get_unique_item_count() == 1
        
        self.inventory.add_item(self.potion)
        assert self.inventory.get_unique_item_count() == 2
    
    def test_get_all_equipment_item_ids(self):
        """装備アイテムID取得テスト"""
        # 通常アイテムを追加
        self.inventory.add_item(self.sword)
        self.inventory.add_item(self.potion)
        
        # 装備アイテムを追加
        self.inventory.add_item(self.fire_sword)
        self.inventory.add_item(self.leather_armor)
        
        equipment_ids = self.inventory.get_all_equipment_item_ids()
        assert "fire_sword" in equipment_ids
        assert "leather_armor" in equipment_ids
        assert "sword" not in equipment_ids  # 通常アイテムは含まれない
        assert "potion" not in equipment_ids  # 通常アイテムは含まれない
    
    def test_get_all_equipment_item_ids_empty(self):
        """装備アイテムがない場合のテスト"""
        self.inventory.add_item(self.sword)
        self.inventory.add_item(self.potion)
        
        equipment_ids = self.inventory.get_all_equipment_item_ids()
        assert equipment_ids == []
    
    def test_complex_scenario(self):
        """複雑なシナリオテスト"""
        # 複数のアイテムを追加
        self.inventory.add_item(self.sword)
        self.inventory.add_item(self.sword)
        self.inventory.add_item(self.potion)
        self.inventory.add_item(self.shield)
        self.inventory.add_item(self.fire_sword)
        self.inventory.add_item(self.leather_armor)
        
        # 状態確認
        assert self.inventory.get_total_item_count() == 6
        assert self.inventory.get_unique_item_count() == 5
        assert self.inventory.get_item_count("sword") == 2
        assert self.inventory.get_item_count("potion") == 1
        
        # 一部削除
        removed = self.inventory.remove_item_by_id("sword", 1)
        assert removed == 1
        assert self.inventory.get_item_count("sword") == 1
        assert self.inventory.get_total_item_count() == 5
        
        # 装備アイテム確認
        equipment_ids = self.inventory.get_all_equipment_item_ids()
        assert len(equipment_ids) == 2
        assert "fire_sword" in equipment_ids
        assert "leather_armor" in equipment_ids
    
    def test_edge_cases(self):
        """エッジケーステスト"""
        # 空のインベントリでの操作
        assert self.inventory.remove_item_by_id("test", 1) == 0
        assert self.inventory.get_item_count("test") == 0
        assert self.inventory.has_item("test") == False
        assert self.inventory.get_item_by_id("test") is None
        
        # 0個の削除
        self.inventory.add_item(self.sword)
        removed = self.inventory.remove_item_by_id("sword", 0)
        assert removed == 0
        assert self.inventory.get_item_count("sword") == 1
        
        # 負の数の削除
        removed = self.inventory.remove_item_by_id("sword", -1)
        assert removed == 0
        assert self.inventory.get_item_count("sword") == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 