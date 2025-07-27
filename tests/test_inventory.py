#!/usr/bin/env python3
"""
Inventoryクラスの包括的なテスト
"""

import pytest
from game.player.inventory import Inventory
from game.item.item import Item
from game.item.equipment_item import Weapon, Armor, WeaponEffect, ArmorEffect
from game.enums import WeaponType, ArmorType, Element, Race, StatusEffectType, DamageType
from game.player.player import Player
from game.player.player_manager import PlayerManager
from game.core.game_context import GameContext
from game.trade.trade_manager import TradeManager
from game.enums import Role


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


class TestInventoryWithUniqueItems:
    """UniqueItemを使ったInventoryのテストクラス"""
    
    def setup_method(self):
        """各テストメソッドの前に実行されるセットアップ"""
        self.inventory = Inventory()
        
        # テスト用UniqueItemを作成
        weapon_effect = WeaponEffect(
            attack_bonus=15,
            critical_rate_bonus=0.1,
            element=Element.FIRE,
            element_damage=10
        )
        self.fire_sword = Weapon(
            "fire_sword", "炎の剣", "火属性の強力な剣",
            WeaponType.SWORD, weapon_effect
        )
        
        armor_effect = ArmorEffect(
            defense_bonus=12,
            speed_bonus=3,
            evasion_bonus=0.05
        )
        self.leather_armor = Armor(
            "leather_armor", "革の鎧", "軽量で動きやすい鎧",
            ArmorType.CHEST, armor_effect
        )
        
        # 別のUniqueItemを作成（同じIDでも異なるインスタンス）
        self.fire_sword_2 = Weapon(
            "fire_sword", "炎の剣", "火属性の強力な剣",
            WeaponType.SWORD, weapon_effect
        )
    
    def test_add_unique_item(self):
        """UniqueItemの追加テスト"""
        self.inventory.add_item(self.fire_sword)
        
        assert self.inventory.get_item_count("fire_sword") == 1
        assert self.inventory.has_item("fire_sword") == True
        assert self.inventory.get_total_item_count() == 1
        assert self.inventory.get_unique_item_count() == 1
        
        # UniqueItemは個別に管理される
        assert len(self.inventory.unique_items) == 1
    
    def test_add_multiple_unique_items(self):
        """複数のUniqueItem追加テスト"""
        self.inventory.add_item(self.fire_sword)
        self.inventory.add_item(self.leather_armor)
        
        assert self.inventory.get_item_count("fire_sword") == 1
        assert self.inventory.get_item_count("leather_armor") == 1
        assert self.inventory.get_total_item_count() == 2
        assert self.inventory.get_unique_item_count() == 2
        
        # 各UniqueItemは個別に管理される
        assert len(self.inventory.unique_items) == 2
    
    def test_add_same_unique_item_type(self):
        """同じタイプのUniqueItemを複数追加するテスト"""
        self.inventory.add_item(self.fire_sword)
        self.inventory.add_item(self.fire_sword_2)  # 同じIDだが異なるインスタンス
        
        assert self.inventory.get_item_count("fire_sword") == 2
        assert self.inventory.get_total_item_count() == 2
        assert self.inventory.get_unique_item_count() == 2
        
        # 各UniqueItemは個別に管理される
        assert len(self.inventory.unique_items) == 2
    
    def test_remove_unique_item(self):
        """UniqueItemの削除テスト"""
        self.inventory.add_item(self.fire_sword)
        
        # UniqueItemの削除
        removed = self.inventory.remove_item_by_id("fire_sword", 1)
        assert removed == 1
        assert self.inventory.get_item_count("fire_sword") == 0
        assert self.inventory.has_item("fire_sword") == False
        assert len(self.inventory.unique_items) == 0
    
    def test_remove_unique_item_with_unique_id(self):
        """UniqueIDを指定したUniqueItemの削除テスト"""
        self.inventory.add_item(self.fire_sword)
        unique_id = self.fire_sword.get_unique_id()
        
        # UniqueIDを指定して削除
        removed = self.inventory.remove_item_by_id("fire_sword", 1, unique_id)
        assert removed == 1
        assert self.inventory.get_item_count("fire_sword") == 0
        assert self.inventory.has_item("fire_sword", unique_id) == False
    
    def test_has_unique_item_with_unique_id(self):
        """UniqueIDを指定したUniqueItemの存在確認テスト"""
        self.inventory.add_item(self.fire_sword)
        unique_id = self.fire_sword.get_unique_id()
        
        assert self.inventory.has_item("fire_sword", unique_id) == True
        assert self.inventory.has_item("fire_sword", "invalid_id") == False
    
    def test_get_items_with_unique_items(self):
        """UniqueItemを含む全アイテムリスト取得テスト"""
        self.inventory.add_item(self.fire_sword)
        self.inventory.add_item(self.leather_armor)
        
        items = self.inventory.get_items()
        assert len(items) == 2
        
        # UniqueItemが正しく含まれていることを確認
        item_ids = [item.item_id for item in items]
        assert "fire_sword" in item_ids
        assert "leather_armor" in item_ids
    
    def test_get_summary_with_unique_items(self):
        """UniqueItemを含むインベントリサマリー取得テスト"""
        self.inventory.add_item(self.fire_sword)
        self.inventory.add_item(self.leather_armor)
        
        summary = self.inventory.get_summary()
        assert "炎の剣" in summary
        assert "革の鎧" in summary
        assert "(固有)" in summary  # UniqueItemの表示
    
    def test_get_inventory_display_with_unique_items(self):
        """UniqueItemを含むインベントリ表示テスト"""
        self.inventory.add_item(self.fire_sword)
        self.inventory.add_item(self.leather_armor)
        
        display = self.inventory.get_inventory_display()
        assert "=== インベントリ ===" in display
        assert "炎の剣" in display
        assert "革の鎧" in display
    
    def test_mixed_items_inventory(self):
        """通常アイテムとUniqueItemが混在するインベントリのテスト"""
        # 通常アイテムを追加
        sword = Item("sword", "鉄の剣", "鉄の剣")
        self.inventory.add_item(sword)
        self.inventory.add_item(sword)  # 重複
        
        # UniqueItemを追加
        self.inventory.add_item(self.fire_sword)
        self.inventory.add_item(self.leather_armor)
        
        # 状態確認
        assert self.inventory.get_item_count("sword") == 2
        assert self.inventory.get_item_count("fire_sword") == 1
        assert self.inventory.get_item_count("leather_armor") == 1
        assert self.inventory.get_total_item_count() == 4
        assert self.inventory.get_unique_item_count() == 3  # sword, fire_sword, leather_armor
        
        # 削除テスト
        removed = self.inventory.remove_item_by_id("sword", 1)
        assert removed == 1
        assert self.inventory.get_item_count("sword") == 1
        
        removed = self.inventory.remove_item_by_id("fire_sword", 1)
        assert removed == 1
        assert self.inventory.get_item_count("fire_sword") == 0
    
    def test_unique_item_durability_tracking(self):
        """UniqueItemの耐久度追跡テスト"""
        # 耐久度を持つUniqueItemを作成
        weapon_effect = WeaponEffect(attack_bonus=10)
        weapon = Weapon(
            "test_weapon", "テスト武器", "テスト用武器",
            WeaponType.SWORD, weapon_effect, max_durability=100
        )
        
        self.inventory.add_item(weapon)
        
        # 耐久度を減らす
        weapon.current_durability = 50
        
        # インベントリから取得して耐久度を確認
        items = self.inventory.get_items()
        retrieved_weapon = items[0]
        assert retrieved_weapon.current_durability == 50
        
        # 表示で耐久度が反映されることを確認
        display = self.inventory.get_inventory_display()
        assert "耐久度" in display or "50" in display


class TestInventoryTradeIntegration:
    """Inventoryと取引システムの連携テスト"""
    
    def setup_method(self):
        """テスト用のプレイヤーとゲームコンテキストをセットアップ"""
        self.player_manager = PlayerManager()
        self.trade_manager = TradeManager()
        self.game_context = GameContext(
            player_manager=self.player_manager,
            spot_manager=None,
            trade_manager=self.trade_manager
        )
        
        # テスト用プレイヤーを作成
        self.seller = Player("seller1", "売り手", Role.ADVENTURER)
        self.buyer = Player("buyer1", "買い手", Role.ADVENTURER)
        
        self.player_manager.add_player(self.seller)
        self.player_manager.add_player(self.buyer)
        
        # テスト用UniqueItemを作成
        weapon_effect = WeaponEffect(attack_bonus=15, element=Element.FIRE)
        self.fire_sword = Weapon(
            "fire_sword", "炎の剣", "火属性の強力な剣",
            WeaponType.SWORD, weapon_effect
        )
        
        armor_effect = ArmorEffect(defense_bonus=12, speed_bonus=3)
        self.leather_armor = Armor(
            "leather_armor", "革の鎧", "軽量で動きやすい鎧",
            ArmorType.CHEST, armor_effect
        )
        
        # 初期アイテムを設定
        self.seller.add_item(self.fire_sword)
        self.buyer.add_item(self.leather_armor)
        self.buyer.status.add_money(1000)
    
    def test_trade_unique_item_inventory_consistency(self):
        """UniqueItem取引時のインベントリ整合性テスト"""
        from game.action.actions.trade_action import PostTradeCommand, AcceptTradeCommand
        
        # 売り手の初期状態を記録
        seller_initial_count = self.seller.get_inventory_item_count("fire_sword")
        seller_inventory_size = len(self.seller.inventory.get_items())
        
        # 取引を実行
        post_command = PostTradeCommand("fire_sword", 1, 500, trade_type="global")
        post_result = post_command.execute(self.seller, self.game_context)
        trade_id = post_result.trade_id
        
        accept_command = AcceptTradeCommand(trade_id)
        accept_result = accept_command.execute(self.buyer, self.game_context)
        
        # 取引完了後のインベントリ状態を確認
        assert accept_result.success is True
        
        # 売り手のインベントリからアイテムが削除されている
        assert self.seller.get_inventory_item_count("fire_sword") == seller_initial_count - 1
        
        # 買い手のインベントリにアイテムが追加されている
        assert self.buyer.get_inventory_item_count("fire_sword") == 1
        
        # インベントリのアイテムリストが正しく更新されている
        seller_items = self.seller.inventory.get_items()
        buyer_items = self.buyer.inventory.get_items()
        
        seller_weapon_count = sum(1 for item in seller_items if item.item_id == "fire_sword")
        buyer_weapon_count = sum(1 for item in buyer_items if item.item_id == "fire_sword")
        
        assert seller_weapon_count == 0
        assert buyer_weapon_count == 1
    
    def test_unique_item_trade_with_equipment_conflict(self):
        """装備中のUniqueItem取引の競合テスト"""
        from game.action.actions.trade_action import PostTradeCommand
        
        # 買い手が革の鎧を装備
        self.buyer.equip_item("leather_armor")
        
        # 装備中のアイテムで取引を試行（失敗するはず）
        command = PostTradeCommand("leather_armor", 1, 300, trade_type="global")
        result = command.execute(self.buyer, self.game_context)
        
        # 結果を検証（装備中のアイテムは取引できない）
        assert result.success is False
        assert "アイテム leather_armor を所持していません" in result.message
    
    def test_unique_item_trade_cancellation_inventory_restoration(self):
        """UniqueItem取引キャンセル時のインベントリ復元テスト"""
        from game.action.actions.trade_action import PostTradeCommand, CancelTradeCommand
        
        # 売り手の初期状態を記録
        seller_initial_count = self.seller.get_inventory_item_count("fire_sword")
        
        # 取引を出品
        post_command = PostTradeCommand("fire_sword", 1, 500, trade_type="global")
        post_result = post_command.execute(self.seller, self.game_context)
        trade_id = post_result.trade_id
        
        # 取引をキャンセル
        cancel_command = CancelTradeCommand(trade_id)
        cancel_result = cancel_command.execute(self.seller, self.game_context)
        
        # キャンセル後のインベントリ状態を確認
        assert cancel_result.success is True
        assert self.seller.get_inventory_item_count("fire_sword") == seller_initial_count
        
        # インベントリのアイテムリストが正しく復元されている
        seller_items = self.seller.inventory.get_items()
        seller_weapon_count = sum(1 for item in seller_items if item.item_id == "fire_sword")
        assert seller_weapon_count == seller_initial_count
    
    def test_unique_item_trade_with_multiple_instances(self):
        """複数インスタンスのUniqueItem取引テスト"""
        from game.action.actions.trade_action import PostTradeCommand, AcceptTradeCommand
        
        # 同じタイプのUniqueItemを複数追加
        weapon_effect = WeaponEffect(attack_bonus=10)
        fire_sword_2 = Weapon("fire_sword", "炎の剣", "火属性の強力な剣", WeaponType.SWORD, weapon_effect)
        
        self.seller.add_item(fire_sword_2)
        
        # 取引を実行
        post_command = PostTradeCommand("fire_sword", 1, 500, trade_type="global")
        post_result = post_command.execute(self.seller, self.game_context)
        trade_id = post_result.trade_id
        
        accept_command = AcceptTradeCommand(trade_id)
        accept_result = accept_command.execute(self.buyer, self.game_context)
        
        # 取引完了後の状態を確認
        assert accept_result.success is True
        
        # 売り手は1つのアイテムを失い、1つ残る
        assert self.seller.get_inventory_item_count("fire_sword") == 1
        
        # 買い手は1つのアイテムを獲得
        assert self.buyer.get_inventory_item_count("fire_sword") == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 