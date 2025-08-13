import pytest
from game.player.equipment_set import EquipmentSet
from game.item.equipment_item import Weapon, Armor, WeaponEffect, ArmorEffect
from game.enums import EquipmentSlot, ArmorType, WeaponType, StatusEffectType, Element, Race


class TestEquipmentSet:
    """EquipmentSetクラスのテスト"""
    
    def setup_method(self):
        """テスト前のセットアップ"""
        self.equipment = EquipmentSet()
        
        # テスト用の武器を作成
        self.weapon_effect = WeaponEffect(
            attack_bonus=15,
            critical_rate_bonus=0.15,
            element=Element.FIRE,
            element_damage=10,
            effective_races={Race.DRAGON},
            race_damage_multiplier=2.0
        )
        
        self.weapon = Weapon(
            item_id="test_sword",
            name="テスト用の剣",
            description="テスト用の剣",
            weapon_type=WeaponType.SWORD,
            effect=self.weapon_effect
        )
        
        # テスト用の防具を作成
        self.helmet_effect = ArmorEffect(
            defense_bonus=8,
            speed_bonus=3,
            evasion_bonus=0.05,
            status_resistance={StatusEffectType.POISON: 0.3}
        )
        
        self.helmet = Armor(
            item_id="test_helmet",
            name="テスト用のヘルメット",
            description="テスト用のヘルメット",
            armor_type=ArmorType.HELMET,
            effect=self.helmet_effect
        )
        
        self.armor_effect = ArmorEffect(
            defense_bonus=12,
            speed_bonus=1,
            evasion_bonus=0.03,
            status_resistance={StatusEffectType.PARALYSIS: 0.2}
        )
        
        self.armor = Armor(
            item_id="test_armor",
            name="テスト用のアーマー",
            description="テスト用のアーマー",
            armor_type=ArmorType.CHEST,
            effect=self.armor_effect
        )
        
        self.shoes_effect = ArmorEffect(
            defense_bonus=5,
            speed_bonus=8,
            evasion_bonus=0.08
        )
        
        self.shoes = Armor(
            item_id="test_shoes",
            name="テスト用のシューズ",
            description="テスト用のシューズ",
            armor_type=ArmorType.SHOES,
            effect=self.shoes_effect
        )
        
        self.gloves_effect = ArmorEffect(
            defense_bonus=3,
            speed_bonus=2,
            evasion_bonus=0.02,
            status_resistance={StatusEffectType.CONFUSION: 0.4}
        )
        
        self.gloves = Armor(
            item_id="test_gloves",
            name="テスト用のグローブ",
            description="テスト用のグローブ",
            armor_type=ArmorType.GLOVES,
            effect=self.gloves_effect
        )
    
    def test_initial_state(self):
        """初期状態のテスト"""
        assert self.equipment.weapon is None
        assert self.equipment.helmet is None
        assert self.equipment.armor is None
        assert self.equipment.shoes is None
        assert self.equipment.gloves is None
    
    def test_get_equipment_bonuses_empty(self):
        """装備なしの場合のボーナス"""
        bonuses = self.equipment.get_equipment_bonuses()
        assert bonuses['attack_bonus'] == 0
        assert bonuses['defense_bonus'] == 0
        assert bonuses['speed_bonus'] == 0
        assert bonuses['critical_rate'] == 0.0
        assert bonuses['evasion_rate'] == 0.0
        assert len(bonuses['status_resistance']) == 0
    
    def test_get_equipment_bonuses_with_weapon(self):
        """武器装備時のボーナス"""
        self.equipment.equip_weapon(self.weapon)
        bonuses = self.equipment.get_equipment_bonuses()
        assert bonuses['attack_bonus'] == 15
        assert bonuses['critical_rate'] == 0.15
    
    def test_get_equipment_bonuses_with_armor(self):
        """防具装備時のボーナス"""
        self.equipment.equip_armor(self.helmet)
        self.equipment.equip_armor(self.armor)
        bonuses = self.equipment.get_equipment_bonuses()
        assert bonuses['defense_bonus'] == 20  # 8 + 12
        assert bonuses['speed_bonus'] == 4  # ヘルメット(3) + アーマー(1)
        assert bonuses['evasion_rate'] == 0.08  # ヘルメット(0.05) + アーマー(0.03)
        assert bonuses['status_resistance'][StatusEffectType.POISON] == 0.3  # ヘルメットのみ
    
    def test_get_equipment_bonuses_with_multiple_armor(self):
        """複数防具装備時のボーナス"""
        self.equipment.equip_armor(self.helmet)
        self.equipment.equip_armor(self.shoes)
        bonuses = self.equipment.get_equipment_bonuses()
        assert bonuses['speed_bonus'] == 11  # 3 + 8
        assert bonuses['evasion_rate'] == 0.13  # 0.05 + 0.08
    
    def test_get_equipment_bonuses_evasion_capped(self):
        """回避率の上限テスト"""
        # 上限を超える回避率を持つ防具を作成
        high_evasion_effect = ArmorEffect(evasion_bonus=1.0)  # 上限値を超える値
        high_evasion_armor = Armor(
            item_id="high_evasion",
            name="高回避防具",
            description="高回避防具",
            armor_type=ArmorType.CHEST,
            effect=high_evasion_effect
        )
        
        self.equipment.equip_armor(high_evasion_armor)
        bonuses = self.equipment.get_equipment_bonuses()
        assert bonuses['evasion_rate'] == 0.95  # 上限値
    
    def test_get_equipment_bonuses_status_resistance(self):
        """状態異常耐性のテスト"""
        self.equipment.equip_armor(self.helmet)
        self.equipment.equip_armor(self.gloves)
        
        bonuses = self.equipment.get_equipment_bonuses()
        # 毒耐性（ヘルメットのみ）
        assert bonuses['status_resistance'][StatusEffectType.POISON] == 0.3
        # 混乱耐性（グローブのみ）
        assert bonuses['status_resistance'][StatusEffectType.CONFUSION] == 0.4
    
    def test_get_equipment_bonuses_status_resistance_capped(self):
        """状態異常耐性の上限テスト"""
        high_resistance_effect = ArmorEffect(status_resistance={StatusEffectType.POISON: 1.0})  # 上限値を超える値
        high_resistance_armor = Armor(
            item_id="high_resistance",
            name="高耐性防具",
            description="高耐性防具",
            armor_type=ArmorType.CHEST,
            effect=high_resistance_effect
        )
        
        self.equipment.equip_armor(high_resistance_armor)
        bonuses = self.equipment.get_equipment_bonuses()
        assert bonuses['status_resistance'][StatusEffectType.POISON] == 0.95  # 上限値
    
    def test_get_equipped_weapons_empty(self):
        """装備なしの場合の装備武器リスト"""
        weapons = self.equipment.get_equipped_weapons()
        assert len(weapons) == 0
    
    def test_get_equipped_weapons_with_weapon(self):
        """武器装備時の装備武器リスト"""
        self.equipment.equip_weapon(self.weapon)
        weapons = self.equipment.get_equipped_weapons()
        assert len(weapons) == 1
        assert weapons[0] == self.weapon
    
    def test_get_equipped_armors_empty(self):
        """装備なしの場合の装備防具リスト"""
        armors = self.equipment.get_equipped_armors()
        assert len(armors) == 0
    
    def test_get_equipped_armors_with_armor(self):
        """防具装備時の装備防具リスト"""
        self.equipment.equip_armor(self.helmet)
        self.equipment.equip_armor(self.armor)
        
        armors = self.equipment.get_equipped_armors()
        assert len(armors) == 2
        assert self.helmet in armors
        assert self.armor in armors
    
    def test_get_equipped_items_empty(self):
        """装備なしの場合の装備アイテム辞書"""
        items = self.equipment.get_equipped_items()
        assert len(items) == 5
        assert all(item is None for item in items.values())
    
    def test_get_equipped_items_with_equipment(self):
        """装備ありの場合の装備アイテム辞書"""
        self.equipment.equip_weapon(self.weapon)
        self.equipment.equip_armor(self.helmet)
        
        items = self.equipment.get_equipped_items()
        assert items[EquipmentSlot.WEAPON] == self.weapon
        assert items[EquipmentSlot.HELMET] == self.helmet
        assert items[EquipmentSlot.CHEST] is None
        assert items[EquipmentSlot.SHOES] is None
        assert items[EquipmentSlot.GLOVES] is None
    
    def test_get_equipped_slots_empty(self):
        """装備なしの場合の装備スロットリスト"""
        slots = self.equipment.get_equipped_slots()
        assert len(slots) == 0
    
    def test_get_equipped_slots_with_equipment(self):
        """装備ありの場合の装備スロットリスト"""
        self.equipment.equip_weapon(self.weapon)
        self.equipment.equip_armor(self.helmet)
        self.equipment.equip_armor(self.shoes)
        
        slots = self.equipment.get_equipped_slots()
        assert len(slots) == 3
        assert EquipmentSlot.WEAPON in slots
        assert EquipmentSlot.HELMET in slots
        assert EquipmentSlot.SHOES in slots
    
    def test_get_available_slots(self):
        """利用可能スロットの取得"""
        slots = self.equipment.get_available_slots()
        assert len(slots) == 5
        assert EquipmentSlot.WEAPON in slots
        assert EquipmentSlot.HELMET in slots
        assert EquipmentSlot.CHEST in slots
        assert EquipmentSlot.SHOES in slots
        assert EquipmentSlot.GLOVES in slots
    
    def test_get_slot_name(self):
        """スロット名の取得"""
        assert self.equipment.get_slot_name(EquipmentSlot.WEAPON) == "武器"
        assert self.equipment.get_slot_name(EquipmentSlot.HELMET) == "ヘルメット"
        assert self.equipment.get_slot_name(EquipmentSlot.CHEST) == "アーマー"
        assert self.equipment.get_slot_name(EquipmentSlot.SHOES) == "シューズ"
        assert self.equipment.get_slot_name(EquipmentSlot.GLOVES) == "グローブ"
    
    def test_equip_weapon(self):
        """武器装備"""
        previous = self.equipment.equip_weapon(self.weapon)
        assert previous is None
        assert self.equipment.weapon == self.weapon
    
    def test_equip_weapon_replace(self):
        """武器装備（既存装備の置き換え）"""
        # 最初の武器を装備
        self.equipment.equip_weapon(self.weapon)
        
        # 新しい武器を作成
        new_weapon_effect = WeaponEffect(attack_bonus=20)
        new_weapon = Weapon(
            item_id="new_sword",
            name="新しい剣",
            description="新しい剣",
            weapon_type=WeaponType.SWORD,
            effect=new_weapon_effect
        )
        
        # 武器を置き換え
        previous = self.equipment.equip_weapon(new_weapon)
        assert previous == self.weapon
        assert self.equipment.weapon == new_weapon
    
    def test_equip_armor_helmet(self):
        """ヘルメット装備"""
        previous = self.equipment.equip_armor(self.helmet)
        assert previous is None
        assert self.equipment.helmet == self.helmet
    
    def test_equip_armor_armor(self):
        """アーマー装備"""
        previous = self.equipment.equip_armor(self.armor)
        assert previous is None
        assert self.equipment.armor == self.armor
    
    def test_equip_armor_shoes(self):
        """シューズ装備"""
        previous = self.equipment.equip_armor(self.shoes)
        assert previous is None
        assert self.equipment.shoes == self.shoes
    
    def test_equip_armor_gloves(self):
        """グローブ装備"""
        previous = self.equipment.equip_armor(self.gloves)
        assert previous is None
        assert self.equipment.gloves == self.gloves
    
    def test_equip_armor_replace(self):
        """防具装備（既存装備の置き換え）"""
        # 最初のヘルメットを装備
        self.equipment.equip_armor(self.helmet)
        
        # 新しいヘルメットを作成
        new_helmet_effect = ArmorEffect(defense_bonus=10)
        new_helmet = Armor(
            item_id="new_helmet",
            name="新しいヘルメット",
            description="新しいヘルメット",
            armor_type=ArmorType.HELMET,
            effect=new_helmet_effect
        )
        
        # ヘルメットを置き換え
        previous = self.equipment.equip_armor(new_helmet)
        assert previous == self.helmet
        assert self.equipment.helmet == new_helmet
    
    def test_unequip_weapon_empty(self):
        """武器解除（装備なし）"""
        weapon = self.equipment.unequip_weapon()
        assert weapon is None
    
    def test_unequip_weapon_with_weapon(self):
        """武器解除（装備あり）"""
        self.equipment.equip_weapon(self.weapon)
        weapon = self.equipment.unequip_weapon()
        assert weapon == self.weapon
        assert self.equipment.weapon is None
    
    def test_unequip_armor_helmet(self):
        """ヘルメット解除"""
        self.equipment.equip_armor(self.helmet)
        armor = self.equipment.unequip_armor(ArmorType.HELMET)
        assert armor == self.helmet
        assert self.equipment.helmet is None
    
    def test_unequip_armor_armor(self):
        """アーマー解除"""
        self.equipment.equip_armor(self.armor)
        armor = self.equipment.unequip_armor(ArmorType.CHEST)
        assert armor == self.armor
        assert self.equipment.armor is None
    
    def test_unequip_armor_shoes(self):
        """シューズ解除"""
        self.equipment.equip_armor(self.shoes)
        armor = self.equipment.unequip_armor(ArmorType.SHOES)
        assert armor == self.shoes
        assert self.equipment.shoes is None
    
    def test_unequip_armor_gloves(self):
        """グローブ解除"""
        self.equipment.equip_armor(self.gloves)
        armor = self.equipment.unequip_armor(ArmorType.GLOVES)
        assert armor == self.gloves
        assert self.equipment.gloves is None
    
    def test_unequip_armor_empty(self):
        """防具解除（装備なし）"""
        armor = self.equipment.unequip_armor(ArmorType.HELMET)
        assert armor is None
    
    def test_unequip_slot_weapon(self):
        """武器スロット解除"""
        self.equipment.equip_weapon(self.weapon)
        item = self.equipment.unequip_slot(EquipmentSlot.WEAPON)
        assert item == self.weapon
        assert self.equipment.weapon is None
    
    def test_unequip_slot_helmet(self):
        """ヘルメットスロット解除"""
        self.equipment.equip_armor(self.helmet)
        item = self.equipment.unequip_slot(EquipmentSlot.HELMET)
        assert item == self.helmet
        assert self.equipment.helmet is None
    
    def test_unequip_slot_armor(self):
        """アーマースロット解除"""
        self.equipment.equip_armor(self.armor)
        item = self.equipment.unequip_slot(EquipmentSlot.CHEST)
        assert item == self.armor
        assert self.equipment.armor is None
    
    def test_unequip_slot_shoes(self):
        """シューズスロット解除"""
        self.equipment.equip_armor(self.shoes)
        item = self.equipment.unequip_slot(EquipmentSlot.SHOES)
        assert item == self.shoes
        assert self.equipment.shoes is None
    
    def test_unequip_slot_gloves(self):
        """グローブスロット解除"""
        self.equipment.equip_armor(self.gloves)
        item = self.equipment.unequip_slot(EquipmentSlot.GLOVES)
        assert item == self.gloves
        assert self.equipment.gloves is None
    
    def test_unequip_slot_empty(self):
        """空スロットの解除"""
        item = self.equipment.unequip_slot(EquipmentSlot.WEAPON)
        assert item is None
    
    def test_str_empty(self):
        """空装備の文字列表現"""
        assert str(self.equipment) == "装備なし"
    
    def test_str_with_equipment(self):
        """装備ありの文字列表現"""
        self.equipment.equip_weapon(self.weapon)
        self.equipment.equip_armor(self.helmet)
        
        result = str(self.equipment)
        assert "武器: test_sword" in result
        assert "頭: test_helmet" in result
        assert "装備:" in result
    
    def test_str_with_all_equipment(self):
        """全装備の文字列表現"""
        self.equipment.equip_weapon(self.weapon)
        self.equipment.equip_armor(self.helmet)
        self.equipment.equip_armor(self.armor)
        self.equipment.equip_armor(self.shoes)
        self.equipment.equip_armor(self.gloves)
        
        result = str(self.equipment)
        assert "武器: test_sword" in result
        assert "頭: test_helmet" in result
        assert "体: test_armor" in result
        assert "足: test_shoes" in result
        assert "手: test_gloves" in result
    
    def test_comprehensive_bonus_calculation(self):
        """包括的なボーナス計算テスト"""
        # 全装備をセット
        self.equipment.equip_weapon(self.weapon)
        self.equipment.equip_armor(self.helmet)
        self.equipment.equip_armor(self.armor)
        self.equipment.equip_armor(self.shoes)
        self.equipment.equip_armor(self.gloves)
        
        # ボーナス計算
        bonuses = self.equipment.get_equipment_bonuses()
        
        # 各ボーナスの検証
        assert bonuses['attack_bonus'] == 15
        assert bonuses['defense_bonus'] == 28  # 8+12+5+3
        assert bonuses['speed_bonus'] == 14   # 3+1+8+2
        assert bonuses['critical_rate'] == 0.15
        assert bonuses['evasion_rate'] == 0.18  # 0.05+0.03+0.08+0.02
        
        # 状態異常耐性の検証
        assert bonuses['status_resistance'][StatusEffectType.POISON] == 0.3
        assert bonuses['status_resistance'][StatusEffectType.PARALYSIS] == 0.2
        assert bonuses['status_resistance'][StatusEffectType.CONFUSION] == 0.4
        assert StatusEffectType.SLEEP not in bonuses['status_resistance'] 