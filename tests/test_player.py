#!/usr/bin/env python3
"""
Playerクラスの包括的なテスト
"""

import pytest
from game.player.player import Player
from game.player.inventory import Inventory
from game.player.equipment_set import EquipmentSet
from game.player.status import Status
from game.item.item import Item
from game.item.equipment_item import Weapon, Armor, WeaponEffect, ArmorEffect
from game.item.consumable_item import ConsumableItem, ItemEffect
from game.enums import Role, EquipmentSlot, WeaponType, ArmorType, Element, Race, StatusEffectType


class TestPlayer:
    """Playerクラスのテストクラス"""
    
    def setup_method(self):
        """各テストメソッドの前に実行されるセットアップ"""
        self.player = Player("test_player_001", "テストプレイヤー", Role.ADVENTURER)
        
        # テスト用アイテムを作成
        self.sword = Item("sword", "鉄の剣")
        self.potion = Item("potion", "回復薬")
        
        # テスト用装備アイテムを作成
        weapon_effect = WeaponEffect(attack_bonus=15, element=Element.FIRE, element_damage=5)
        self.fire_sword = Weapon("fire_sword", "炎の剣", WeaponType.SWORD, weapon_effect)
        
        armor_effect = ArmorEffect(defense_bonus=8, evasion_bonus=0.1)
        self.leather_armor = Armor("leather_armor", "革の鎧", ArmorType.CHEST, armor_effect)
        
        # テスト用消費アイテムを作成
        effect = ItemEffect(hp_restore=50, mp_restore=20)
        self.healing_potion = ConsumableItem("healing_potion", "回復薬", effect)
        
        effect2 = ItemEffect(hp_restore=100, attack_boost=10, duration=3)
        self.power_potion = ConsumableItem("power_potion", "パワーポーション", effect2)
    
    def test_player_initialization(self):
        """プレイヤーの初期化テスト"""
        assert self.player.player_id == "test_player_001"
        assert self.player.name == "テストプレイヤー"
        assert self.player.role == Role.ADVENTURER
        assert self.player.current_spot_id is None
        assert isinstance(self.player.inventory, Inventory)
        assert isinstance(self.player.equipment, EquipmentSet)
        assert isinstance(self.player.status, Status)
    
    def test_get_player_id(self):
        """プレイヤーID取得テスト"""
        assert self.player.get_player_id() == "test_player_001"
    
    def test_get_current_spot_id(self):
        """現在位置ID取得テスト"""
        assert self.player.get_current_spot_id() is None
        
        self.player.set_current_spot_id("town_square")
        assert self.player.get_current_spot_id() == "town_square"
    
    def test_set_current_spot_id(self):
        """現在位置ID設定テスト"""
        self.player.set_current_spot_id("inn")
        assert self.player.current_spot_id == "inn"
        assert self.player.get_current_spot_id() == "inn"
    
    def test_get_role(self):
        """ロール取得テスト"""
        assert self.player.get_role() == Role.ADVENTURER
    
    def test_set_role(self):
        """ロール設定テスト"""
        self.player.set_role(Role.MERCHANT)
        assert self.player.role == Role.MERCHANT
        assert self.player.get_role() == Role.MERCHANT
    
    def test_is_role(self):
        """ロール判定テスト"""
        assert self.player.is_role(Role.ADVENTURER) == True
        assert self.player.is_role(Role.MERCHANT) == False
        
        self.player.set_role(Role.MERCHANT)
        assert self.player.is_role(Role.MERCHANT) == True
        assert self.player.is_role(Role.ADVENTURER) == False
    
    def test_get_inventory(self):
        """インベントリ取得テスト"""
        inventory = self.player.get_inventory()
        assert isinstance(inventory, Inventory)
        assert inventory == self.player.inventory
    
    def test_set_inventory(self):
        """インベントリ設定テスト"""
        new_inventory = Inventory()
        new_inventory.add_item(self.sword)
        
        self.player.set_inventory(new_inventory)
        assert self.player.inventory == new_inventory
        assert self.player.get_inventory() == new_inventory
        assert self.player.inventory.has_item("sword")
    
    def test_get_equipment(self):
        """装備セット取得テスト"""
        equipment = self.player.get_equipment()
        assert isinstance(equipment, EquipmentSet)
        assert equipment == self.player.equipment
    
    def test_set_equipment(self):
        """装備セット設定テスト"""
        new_equipment = EquipmentSet()
        self.player.set_equipment(new_equipment)
        assert self.player.equipment == new_equipment
        assert self.player.get_equipment() == new_equipment
    
    def test_get_status(self):
        """ステータス取得テスト"""
        status = self.player.get_status()
        assert isinstance(status, Status)
        assert status == self.player.status
    
    def test_set_status(self):
        """ステータス設定テスト"""
        new_status = Status()
        new_status.set_hp(200)
        new_status.set_mp(150)
        
        self.player.set_status(new_status)
        assert self.player.status == new_status
        assert self.player.get_status() == new_status
        assert self.player.status.get_hp() == 200
        assert self.player.status.get_mp() == 150
    
    def test_get_current_status_snapshot(self):
        """現在ステータススナップショット取得テスト"""
        # 初期状態のスナップショット
        snapshot = self.player.get_current_status_snapshot()
        assert 'hp' in snapshot
        assert 'mp' in snapshot
        assert 'attack' in snapshot
        assert 'defense' in snapshot
        assert 'money' in snapshot
        assert 'experience_points' in snapshot
        
        # ステータス変更後のスナップショット
        self.player.status.set_hp(150)
        self.player.status.set_mp(100)
        self.player.status.set_attack(25)
        self.player.status.set_defense(15)
        self.player.status.set_money(1000)
        self.player.status.set_experience_points(500)
        
        snapshot2 = self.player.get_current_status_snapshot()
        assert snapshot2['hp'] == 150
        assert snapshot2['mp'] == 100
        assert snapshot2['attack'] == 25
        assert snapshot2['defense'] == 15
        assert snapshot2['money'] == 1000
        assert snapshot2['experience_points'] == 500
    
    def test_use_item_success(self):
        """アイテム使用成功テスト"""
        # インベントリに消費アイテムを追加
        self.player.inventory.add_item(self.healing_potion)
        
        # 使用前のステータスを記録
        hp_before = self.player.status.get_hp()
        mp_before = self.player.status.get_mp()
        
        # アイテムを使用
        result = self.player.use_item("healing_potion")
        
        # 結果を検証
        assert result.success == True
        assert "アイテムを使用しました" in result.message
        assert result.item_id == "healing_potion"
        assert result.effect == self.healing_potion.effect
        
        # ステータス変化を検証
        assert self.player.status.get_hp() == hp_before + 50
        assert self.player.status.get_mp() == mp_before + 20
        
        # インベントリから削除されたことを確認
        assert not self.player.inventory.has_item("healing_potion")
        
        # スナップショットの検証
        assert result.status_before['hp'] == hp_before
        assert result.status_after['hp'] == hp_before + 50
    
    def test_use_item_not_found(self):
        """存在しないアイテム使用テスト"""
        result = self.player.use_item("nonexistent_item")
        
        assert result.success == False
        assert "アイテムが見つかりません" in result.message
        assert result.item_id == "nonexistent_item"
    
    def test_use_item_not_consumable(self):
        """消費できないアイテム使用テスト"""
        self.player.inventory.add_item(self.sword)
        
        result = self.player.use_item("sword")
        
        assert result.success == False
        assert "アイテムが使用できません" in result.message
        assert result.item_id == "sword"
    
    def test_use_item_cannot_consume(self):
        """使用条件を満たさないアイテム使用テスト"""
        # 使用条件を満たさない消費アイテムを作成
        effect = ItemEffect(hp_restore=50, mp_cost=1000)  # MPが足りない
        high_mp_potion = ConsumableItem("high_mp_potion", "高MP消費薬", effect)
        
        self.player.inventory.add_item(high_mp_potion)
        
        result = self.player.use_item("high_mp_potion")
        
        assert result.success == False
        assert "アイテムが使用できません" in result.message
        assert result.item_id == "high_mp_potion"
    
    def test_preview_item_effect_success(self):
        """アイテム効果プレビュー成功テスト"""
        self.player.inventory.add_item(self.healing_potion)
        
        effect = self.player.preview_item_effect("healing_potion")
        
        assert effect is not None
        assert effect.hp_restore == 50
        assert effect.mp_restore == 20
    
    def test_preview_item_effect_not_found(self):
        """存在しないアイテムの効果プレビューテスト"""
        effect = self.player.preview_item_effect("nonexistent_item")
        assert effect is None
    
    def test_preview_item_effect_not_consumable(self):
        """消費アイテムでないアイテムの効果プレビューテスト"""
        self.player.inventory.add_item(self.sword)
        
        effect = self.player.preview_item_effect("sword")
        assert effect is None
    
    def test_has_item(self):
        """アイテム所持判定テスト"""
        assert self.player.has_item("sword") == False
        
        self.player.inventory.add_item(self.sword)
        assert self.player.has_item("sword") == True
        
        self.player.inventory.remove_item_by_id("sword", 1)
        assert self.player.has_item("sword") == False
    
    def test_equip_item_weapon_success(self):
        """武器装備成功テスト"""
        self.player.inventory.add_item(self.fire_sword)
        
        result = self.player.equip_item("fire_sword")
        
        assert result.success == True
        assert "武器を装備しました" in result.message
        assert result.item_id == "fire_sword"
        assert result.replaced_item_id is None
        
        # インベントリから削除されたことを確認
        assert not self.player.inventory.has_item("fire_sword")
    
    def test_equip_item_armor_success(self):
        """防具装備成功テスト"""
        self.player.inventory.add_item(self.leather_armor)
        
        result = self.player.equip_item("leather_armor")
        
        assert result.success == True
        assert "防具を装備しました" in result.message
        assert result.item_id == "leather_armor"
        assert result.replaced_item_id is None
        
        # インベントリから削除されたことを確認
        assert not self.player.inventory.has_item("leather_armor")
    
    def test_equip_item_not_found(self):
        """存在しないアイテム装備テスト"""
        result = self.player.equip_item("nonexistent_item")
        
        assert result.success == False
        assert "アイテムが見つかりません" in result.message
        assert result.item_id == "nonexistent_item"
    
    def test_equip_item_not_equipment(self):
        """装備できないアイテム装備テスト"""
        self.player.inventory.add_item(self.sword)
        
        result = self.player.equip_item("sword")
        
        assert result.success == False
        assert "アイテムを装備できません" in result.message
        assert result.item_id == "sword"
    
    def test_equip_item_replace_weapon(self):
        """武器装備時の既存装備置換テスト"""
        # 既存の武器を装備
        self.player.inventory.add_item(self.fire_sword)
        self.player.equip_item("fire_sword")
        
        # 新しい武器を作成して装備
        new_weapon_effect = WeaponEffect(attack_bonus=20, element=Element.ICE)
        new_weapon = Weapon("ice_sword", "氷の剣", WeaponType.SWORD, new_weapon_effect)
        self.player.inventory.add_item(new_weapon)
        
        result = self.player.equip_item("ice_sword")
        
        assert result.success == True
        assert "武器を装備しました" in result.message
        assert result.item_id == "ice_sword"
        assert result.replaced_item_id == "fire_sword"
        
        # 既存の武器がインベントリに戻されたことを確認
        assert self.player.inventory.has_item("fire_sword")
        assert not self.player.inventory.has_item("ice_sword")
    
    def test_unequip_slot_weapon_success(self):
        """武器外し成功テスト"""
        # 武器を装備
        self.player.inventory.add_item(self.fire_sword)
        self.player.equip_item("fire_sword")
        
        result = self.player.unequip_slot(EquipmentSlot.WEAPON)
        
        assert result.success == True
        assert "武器を外しました" in result.message
        assert result.item_id == "fire_sword"
        
        # インベントリに戻されたことを確認
        assert self.player.inventory.has_item("fire_sword")
    
    def test_unequip_slot_armor_success(self):
        """防具外し成功テスト"""
        # 防具を装備
        self.player.inventory.add_item(self.leather_armor)
        self.player.equip_item("leather_armor")
        
        result = self.player.unequip_slot(EquipmentSlot.CHEST)
        
        assert result.success == True
        assert "胴体を外しました" in result.message
        assert result.item_id == "leather_armor"
        
        # インベントリに戻されたことを確認
        assert self.player.inventory.has_item("leather_armor")
    
    def test_unequip_slot_empty(self):
        """空のスロット外しテスト"""
        result = self.player.unequip_slot(EquipmentSlot.WEAPON)
        
        assert result.success == False
        assert "武器を装備していないため外せません" in result.message
        assert result.item_id is None
    
    def test_property_hp(self):
        """HPプロパティテスト"""
        self.player.status.set_hp(150)
        assert self.player.hp == 150
    
    def test_property_mp(self):
        """MPプロパティテスト"""
        self.player.status.set_mp(100)
        assert self.player.mp == 100
    
    def test_property_attack(self):
        """攻撃力プロパティテスト"""
        self.player.status.set_attack(20)
        assert self.player.attack == 20
        
        # 装備ボーナスを追加
        self.player.inventory.add_item(self.fire_sword)
        self.player.equip_item("fire_sword")
        assert self.player.attack == 20 + 15  # 基本攻撃力 + 武器ボーナス
    
    def test_property_defense(self):
        """防御力プロパティテスト"""
        self.player.status.set_defense(15)
        assert self.player.defense == 15
        
        # 装備ボーナスを追加
        self.player.inventory.add_item(self.leather_armor)
        self.player.equip_item("leather_armor")
        assert self.player.defense == 15 + 8  # 基本防御力 + 防具ボーナス
    
    def test_property_speed(self):
        """素早さプロパティテスト"""
        self.player.status.set_speed(10)
        assert self.player.speed == 10
        
        # 装備ボーナスを追加
        self.player.inventory.add_item(self.leather_armor)
        self.player.equip_item("leather_armor")
        # 防具に素早さボーナスがない場合は基本値のまま
        assert self.player.speed == 10
    
    def test_property_critical_rate(self):
        """クリティカル率プロパティテスト"""
        self.player.status.set_critical_rate(0.1)
        assert self.player.critical_rate == 0.1
        
        # 装備ボーナスを追加
        self.player.inventory.add_item(self.fire_sword)
        self.player.equip_item("fire_sword")
        # 武器にクリティカル率ボーナスがない場合は基本値のまま
        assert self.player.critical_rate == 0.1
    
    def test_property_evasion_rate(self):
        """回避率プロパティテスト"""
        self.player.status.set_evasion_rate(0.05)
        assert self.player.evasion_rate == 0.05
        
        # 装備ボーナスを追加
        self.player.inventory.add_item(self.leather_armor)
        self.player.equip_item("leather_armor")
        assert self.player.evasion_rate == 0.05 + 0.1  # 基本回避率 + 防具ボーナス
    
    def test_get_status_summary(self):
        """ステータスサマリー取得テスト"""
        self.player.status.set_hp(150)
        self.player.status.set_mp(100)
        self.player.status.set_attack(25)
        self.player.status.set_defense(15)
        self.player.status.set_speed(10)
        self.player.status.set_critical_rate(0.1)
        self.player.status.set_evasion_rate(0.05)
        
        summary = self.player.get_status_summary()
        
        assert "HP: 150/" in summary
        assert "MP: 100/" in summary
        assert "攻撃: 25" in summary
        assert "防御: 15" in summary
        assert "素早さ: 10" in summary
        assert "クリティカル: 10.0%" in summary
        assert "回避: 5.0%" in summary
    
    def test_comprehensive_scenario(self):
        """包括的なシナリオテスト"""
        # 1. プレイヤーの初期状態確認
        assert self.player.role == Role.ADVENTURER
        assert self.player.hp == self.player.status.get_hp()
        assert self.player.mp == self.player.status.get_mp()
        
        # 2. アイテムをインベントリに追加
        self.player.inventory.add_item(self.healing_potion)
        self.player.inventory.add_item(self.fire_sword)
        self.player.inventory.add_item(self.leather_armor)
        
        assert self.player.has_item("healing_potion")
        assert self.player.has_item("fire_sword")
        assert self.player.has_item("leather_armor")
        
        # 3. アイテムを使用
        hp_before = self.player.hp
        result = self.player.use_item("healing_potion")
        assert result.success
        assert self.player.hp == hp_before + 50
        assert not self.player.has_item("healing_potion")
        
        # 4. 装備を装着
        result = self.player.equip_item("fire_sword")
        assert result.success
        assert self.player.attack > 0  # 装備ボーナスが反映される
        
        result = self.player.equip_item("leather_armor")
        assert result.success
        assert self.player.defense > 0  # 装備ボーナスが反映される
        
        # 5. 装備を外す
        result = self.player.unequip_slot(EquipmentSlot.WEAPON)
        assert result.success
        assert self.player.has_item("fire_sword")
        
        # 6. ステータスサマリーの確認
        summary = self.player.get_status_summary()
        assert "HP:" in summary
        assert "MP:" in summary
        assert "攻撃:" in summary
        assert "防御:" in summary
    
    def test_edge_cases(self):
        """エッジケーステスト"""
        # 空のインベントリでのアイテム使用
        result = self.player.use_item("nonexistent")
        assert not result.success
        
        # 存在しないスロットの外し
        result = self.player.unequip_slot(EquipmentSlot.WEAPON)
        assert not result.success
        
        # ロール変更
        self.player.set_role(Role.MERCHANT)
        assert self.player.is_role(Role.MERCHANT)
        assert not self.player.is_role(Role.ADVENTURER)
        
        # 位置変更
        self.player.set_current_spot_id("new_location")
        assert self.player.get_current_spot_id() == "new_location" 