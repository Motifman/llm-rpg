import pytest
from unittest.mock import Mock, MagicMock
from dataclasses import dataclass

from game.item.item import Item
from game.item.item_effect import ItemEffect
from game.item.consumable_item import ConsumableItem
from game.item.equipment_item import Weapon, Armor, WeaponEffect, ArmorEffect
from game.enums import Element, Race, StatusEffectType, DamageType, WeaponType, ArmorType
from game.player.status import StatusEffect


class TestItem:
    """基本的なアイテムクラスのテスト"""
    
    def test_item_creation(self):
        """アイテムの作成テスト"""
        item = Item("test_item", "テストアイテム")
        assert item.item_id == "test_item"
        assert item.description == "テストアイテム"
    
    def test_item_str_representation(self):
        """アイテムの文字列表現テスト"""
        item = Item("sword", "鉄の剣")
        assert str(item) == "sword - 鉄の剣"
    
    def test_item_repr_representation(self):
        """アイテムのrepr表現テスト"""
        item = Item("potion", "回復薬")
        expected = "Item(item_id=potion, description=回復薬)"
        assert repr(item) == expected
    
    def test_item_immutability(self):
        """アイテムの不変性テスト"""
        item = Item("test", "テスト")
        # frozen=Trueなので属性変更はできない
        with pytest.raises(Exception):
            item.item_id = "new_id"


class TestItemEffect:
    """アイテム効果クラスのテスト"""
    
    def test_item_effect_creation(self):
        """アイテム効果の作成テスト"""
        effect = ItemEffect(hp_change=50, mp_change=20)
        assert effect.hp_change == 50
        assert effect.mp_change == 20
    
    def test_item_effect_with_all_parameters(self):
        """全パラメータでのアイテム効果作成テスト"""
        effect = ItemEffect(
            hp_change=100,
            mp_change=50,
            money_change=1000,
            experience_change=500
        )
        assert effect.hp_change == 100
        assert effect.mp_change == 50
        assert effect.money_change == 1000
        assert effect.experience_change == 500
    
    def test_item_effect_str_representation(self):
        """アイテム効果の文字列表現テスト"""
        effect = ItemEffect(hp_change=50, mp_change=20)
        assert "HP+50" in str(effect)
        assert "MP+20" in str(effect)
    
    def test_item_effect_str_with_negative_values(self):
        """負の値での文字列表現テスト"""
        effect = ItemEffect(hp_change=-20, mp_change=-10)
        assert "HP-20" in str(effect)
        assert "MP-10" in str(effect)
    
    def test_item_effect_str_with_temporary_effects(self):
        """一時効果付きの文字列表現テスト"""
        status_effect = StatusEffect(StatusEffectType.POISON, 3, 10)
        effect = ItemEffect(temporary_effects=[status_effect])
        assert "poison: 3ターン" in str(effect)
    
    def test_item_effect_str_no_effects(self):
        """効果なしの場合の文字列表現テスト"""
        effect = ItemEffect()
        assert str(effect) == "効果なし"
    
    def test_item_effect_immutability(self):
        """アイテム効果の不変性テスト"""
        effect = ItemEffect(hp_change=50)
        # frozen=Trueなので属性変更はできない
        with pytest.raises(Exception):
            effect.hp_change = 100


class TestConsumableItem:
    """消費アイテムクラスのテスト"""
    
    def test_consumable_item_creation(self):
        """消費アイテムの作成テスト"""
        effect = ItemEffect(hp_change=50)
        item = ConsumableItem("potion", "回復薬", effect)
        assert item.item_id == "potion"
        assert item.description == "回復薬"
        assert item.effect == effect
        assert item.max_stack == 1
    
    def test_consumable_item_with_custom_stack(self):
        """カスタムスタック数での消費アイテム作成テスト"""
        effect = ItemEffect(hp_change=30)
        item = ConsumableItem("herb", "薬草", effect, max_stack=10)
        assert item.max_stack == 10
    
    def test_consumable_item_can_consume(self):
        """消費可能判定テスト"""
        effect = ItemEffect(hp_change=50)
        item = ConsumableItem("potion", "回復薬", effect)
        
        # モックプレイヤーを作成
        mock_player = Mock()
        mock_player.has_item.return_value = True
        
        assert item.can_consume(mock_player) == True
        
        # インベントリにアイテムがない場合
        mock_player.has_item.return_value = False
        assert item.can_consume(mock_player) == False
    
    def test_consumable_item_str_representation(self):
        """消費アイテムの文字列表現テスト"""
        effect = ItemEffect(hp_change=50, mp_change=20)
        item = ConsumableItem("elixir", "万能薬", effect)
        assert "elixir - 万能薬" in str(item)
        assert "HP+50" in str(item)
        assert "MP+20" in str(item)
    
    def test_consumable_item_repr_representation(self):
        """消費アイテムのrepr表現テスト"""
        effect = ItemEffect(hp_change=50)
        item = ConsumableItem("potion", "回復薬", effect, max_stack=5)
        expected = "ConsumableItem(item_id=potion, description=回復薬, effect=効果: HP+50, max_stack=5)"
        assert repr(item) == expected


class TestWeaponEffect:
    """武器効果クラスのテスト"""
    
    def test_weapon_effect_creation(self):
        """武器効果の作成テスト"""
        effect = WeaponEffect(attack_bonus=10)
        assert effect.attack_bonus == 10
        assert effect.element is None
        assert effect.element_damage == 0
        assert effect.effective_races == set()
        assert effect.race_damage_multiplier == 1.5
        assert effect.status_effects == {}
        assert effect.status_chance == 0.0
        assert effect.critical_rate_bonus == 0.0
    
    def test_weapon_effect_with_element(self):
        """属性付き武器効果の作成テスト"""
        effect = WeaponEffect(
            attack_bonus=15,
            element=Element.FIRE,
            element_damage=20
        )
        assert effect.attack_bonus == 15
        assert effect.element == Element.FIRE
        assert effect.element_damage == 20
    
    def test_weapon_effect_with_race_effectiveness(self):
        """種族特攻付き武器効果の作成テスト"""
        effect = WeaponEffect(
            attack_bonus=20,
            effective_races={Race.DRAGON, Race.DEMON},
            race_damage_multiplier=2.0
        )
        assert effect.attack_bonus == 20
        assert Race.DRAGON in effect.effective_races
        assert Race.DEMON in effect.effective_races
        assert effect.race_damage_multiplier == 2.0
    
    def test_weapon_effect_str_representation(self):
        """武器効果の文字列表現テスト"""
        effect = WeaponEffect(attack_bonus=15, element=Element.FIRE, element_damage=20)
        assert "攻撃力+15" in str(effect)
        assert "fire属性+20" in str(effect)
    
    def test_weapon_effect_str_with_race_effectiveness(self):
        """種族特攻付きの文字列表現テスト"""
        effect = WeaponEffect(
            attack_bonus=20,
            effective_races={Race.DRAGON, Race.DEMON}
        )
        assert "攻撃力+20" in str(effect)
        # 順序は不定なので、両方のパターンをチェック
        effect_str = str(effect)
        assert "特攻: dragon, demon" in effect_str or "特攻: demon, dragon" in effect_str
    
    def test_weapon_effect_str_with_status_effects(self):
        """状態異常付きの文字列表現テスト"""
        status_effect = StatusEffect(StatusEffectType.POISON, 3, 10)
        effect = WeaponEffect(
            attack_bonus=10,
            status_effects={StatusEffectType.POISON: status_effect},
            status_chance=0.3
        )
        assert "攻撃力+10" in str(effect)
        assert "状態異常" in str(effect)
    
    def test_weapon_effect_str_with_critical_bonus(self):
        """クリティカルボーナス付きの文字列表現テスト"""
        effect = WeaponEffect(attack_bonus=10, critical_rate_bonus=0.15)
        assert "攻撃力+10" in str(effect)
        assert "クリティカル+15.0%" in str(effect)
    
    def test_weapon_effect_str_no_special_effects(self):
        """特殊効果なしの場合の文字列表現テスト"""
        effect = WeaponEffect()
        assert str(effect) == "特殊効果なし"


class TestWeapon:
    """武器クラスのテスト"""
    
    def test_weapon_creation(self):
        """武器の作成テスト"""
        weapon_effect = WeaponEffect(attack_bonus=15)
        weapon = Weapon("iron_sword", "鉄の剣", WeaponType.SWORD, weapon_effect)
        assert weapon.item_id == "iron_sword"
        assert weapon.description == "鉄の剣"
        assert weapon.weapon_type == WeaponType.SWORD
        assert weapon.effect == weapon_effect
        assert weapon.rarity == "common"
    
    def test_weapon_with_custom_rarity(self):
        """カスタムレアリティでの武器作成テスト"""
        weapon_effect = WeaponEffect(attack_bonus=30)
        weapon = Weapon("legendary_sword", "伝説の剣", WeaponType.SWORD, weapon_effect, "legendary")
        assert weapon.rarity == "legendary"
    
    def test_weapon_calculate_damage_basic(self):
        """基本的なダメージ計算テスト"""
        weapon_effect = WeaponEffect(attack_bonus=20)
        weapon = Weapon("sword", "剣", WeaponType.SWORD, weapon_effect)
        
        damage = weapon.calculate_damage(50)  # 基本攻撃力50
        assert damage == 70  # 50 + 20
    
    def test_weapon_calculate_damage_with_element(self):
        """属性ダメージ付きのダメージ計算テスト"""
        weapon_effect = WeaponEffect(
            attack_bonus=15,
            element=Element.FIRE,
            element_damage=25
        )
        weapon = Weapon("fire_sword", "炎の剣", WeaponType.SWORD, weapon_effect)
        
        damage = weapon.calculate_damage(40)  # 基本攻撃力40
        assert damage == 80  # 40 + 15 + 25
    
    def test_weapon_calculate_damage_with_race_effectiveness(self):
        """種族特攻付きのダメージ計算テスト"""
        weapon_effect = WeaponEffect(
            attack_bonus=10,
            effective_races={Race.DRAGON},
            race_damage_multiplier=2.0
        )
        weapon = Weapon("dragon_slayer", "竜殺し", WeaponType.SWORD, weapon_effect)
        
        # 竜族へのダメージ
        damage = weapon.calculate_damage(30, Race.DRAGON)
        assert damage == 80  # (30 + 10) * 2.0
        
        # 他の種族へのダメージ
        damage = weapon.calculate_damage(30, Race.HUMAN)
        assert damage == 40  # 30 + 10（特攻なし）
    
    def test_weapon_get_critical_rate(self):
        """武器のクリティカル率取得テスト"""
        weapon_effect = WeaponEffect(critical_rate_bonus=0.25)
        weapon = Weapon("critical_sword", "クリティカル剣", WeaponType.SWORD, weapon_effect)
        
        assert weapon.get_critical_rate() == 0.25
    
    def test_weapon_str_representation(self):
        """武器の文字列表現テスト"""
        weapon_effect = WeaponEffect(attack_bonus=20, element=Element.FIRE, element_damage=15)
        weapon = Weapon("fire_sword", "炎の剣", WeaponType.SWORD, weapon_effect)
        
        assert "fire_sword (sword) - 炎の剣" in str(weapon)
        assert "攻撃力+20" in str(weapon)
        assert "fire属性+15" in str(weapon)


class TestArmorEffect:
    """防具効果クラスのテスト"""
    
    def test_armor_effect_creation(self):
        """防具効果の作成テスト"""
        effect = ArmorEffect(defense_bonus=15)
        assert effect.defense_bonus == 15
        assert effect.counter_damage == 0
        assert effect.counter_chance == 0.0
        assert effect.status_resistance == {}
        assert effect.damage_reduction == {}
        assert effect.evasion_bonus == 0.0
        assert effect.speed_bonus == 0
    
    def test_armor_effect_with_counter(self):
        """反撃付き防具効果の作成テスト"""
        effect = ArmorEffect(
            defense_bonus=20,
            counter_damage=30,
            counter_chance=0.25
        )
        assert effect.defense_bonus == 20
        assert effect.counter_damage == 30
        assert effect.counter_chance == 0.25
    
    def test_armor_effect_with_resistances(self):
        """耐性付き防具効果の作成テスト"""
        effect = ArmorEffect(
            defense_bonus=10,
            status_resistance={StatusEffectType.POISON: 0.5},
            damage_reduction={DamageType.MAGICAL: 0.3}
        )
        assert effect.defense_bonus == 10
        assert effect.status_resistance[StatusEffectType.POISON] == 0.5
        assert effect.damage_reduction[DamageType.MAGICAL] == 0.3
    
    def test_armor_effect_str_representation(self):
        """防具効果の文字列表現テスト"""
        effect = ArmorEffect(defense_bonus=20, evasion_bonus=0.15, speed_bonus=5)
        assert "防御力+20" in str(effect)
        assert "回避+15.0%" in str(effect)
        assert "素早さ+5" in str(effect)
    
    def test_armor_effect_str_with_counter(self):
        """反撃付きの文字列表現テスト"""
        effect = ArmorEffect(
            defense_bonus=15,
            counter_damage=25,
            counter_chance=0.3
        )
        assert "防御力+15" in str(effect)
        assert "反撃(30.0%)" in str(effect)
    
    def test_armor_effect_str_with_resistances(self):
        """耐性付きの文字列表現テスト"""
        effect = ArmorEffect(
            defense_bonus=10,
            status_resistance={StatusEffectType.POISON: 0.5, StatusEffectType.PARALYSIS: 0.3},
            damage_reduction={DamageType.MAGICAL: 0.4}
        )
        assert "防御力+10" in str(effect)
        assert "耐性: poison耐性50.0%, paralysis耐性30.0%" in str(effect)
        assert "軽減: magical軽減40.0%" in str(effect)
    
    def test_armor_effect_str_no_special_effects(self):
        """特殊効果なしの場合の文字列表現テスト"""
        effect = ArmorEffect()
        assert str(effect) == "特殊効果なし"


class TestArmor:
    """防具クラスのテスト"""
    
    def test_armor_creation(self):
        """防具の作成テスト"""
        armor_effect = ArmorEffect(defense_bonus=20)
        armor = Armor("iron_armor", "鉄の鎧", ArmorType.CHEST, armor_effect)
        assert armor.item_id == "iron_armor"
        assert armor.description == "鉄の鎧"
        assert armor.armor_type == ArmorType.CHEST
        assert armor.effect == armor_effect
        assert armor.rarity == "common"
    
    def test_armor_with_custom_rarity(self):
        """カスタムレアリティでの防具作成テスト"""
        armor_effect = ArmorEffect(defense_bonus=30)
        armor = Armor("legendary_armor", "伝説の鎧", ArmorType.CHEST, armor_effect, "legendary")
        assert armor.rarity == "legendary"
    
    def test_armor_calculate_defense_bonus(self):
        """防具の防御ボーナス計算テスト"""
        armor_effect = ArmorEffect(defense_bonus=25)
        armor = Armor("armor", "鎧", ArmorType.CHEST, armor_effect)
        
        assert armor.calculate_defense_bonus() == 25
    
    def test_armor_get_damage_reduction(self):
        """防具のダメージ軽減取得テスト"""
        armor_effect = ArmorEffect(damage_reduction={DamageType.MAGICAL: 0.4})
        armor = Armor("magic_armor", "魔法の鎧", ArmorType.CHEST, armor_effect)
        
        assert armor.get_damage_reduction(DamageType.MAGICAL) == 0.4
        assert armor.get_damage_reduction(DamageType.PHYSICAL) == 0.0  # 設定されていない
    
    def test_armor_get_status_resistance(self):
        """防具の状態異常耐性取得テスト"""
        armor_effect = ArmorEffect(status_resistance={StatusEffectType.POISON: 0.5})
        armor = Armor("poison_armor", "毒耐性鎧", ArmorType.CHEST, armor_effect)
        
        assert armor.get_status_resistance(StatusEffectType.POISON) == 0.5
        assert armor.get_status_resistance(StatusEffectType.PARALYSIS) == 0.0  # 設定されていない
    
    def test_armor_get_counter_chance(self):
        """防具の反撃確率取得テスト"""
        armor_effect = ArmorEffect(counter_chance=0.3)
        armor = Armor("counter_armor", "反撃鎧", ArmorType.CHEST, armor_effect)
        
        assert armor.get_counter_chance() == 0.3
    
    def test_armor_get_counter_damage(self):
        """防具の反撃ダメージ取得テスト"""
        armor_effect = ArmorEffect(counter_damage=40)
        armor = Armor("counter_armor", "反撃鎧", ArmorType.CHEST, armor_effect)
        
        assert armor.get_counter_damage() == 40
    
    def test_armor_get_evasion_bonus(self):
        """防具の回避ボーナス取得テスト"""
        armor_effect = ArmorEffect(evasion_bonus=0.2)
        armor = Armor("evasion_armor", "回避鎧", ArmorType.CHEST, armor_effect)
        
        assert armor.get_evasion_bonus() == 0.2
    
    def test_armor_get_speed_bonus(self):
        """防具の素早さボーナス取得テスト"""
        armor_effect = ArmorEffect(speed_bonus=10)
        armor = Armor("speed_armor", "素早さ鎧", ArmorType.CHEST, armor_effect)
        
        assert armor.get_speed_bonus() == 10
    
    def test_armor_str_representation(self):
        """防具の文字列表現テスト"""
        armor_effect = ArmorEffect(defense_bonus=25, evasion_bonus=0.1)
        armor = Armor("iron_armor", "鉄の鎧", ArmorType.CHEST, armor_effect)
        
        assert "iron_armor (chest) - 鉄の鎧" in str(armor)
        assert "防御力+25" in str(armor)
        assert "回避+10.0%" in str(armor)


class TestItemIntegration:
    """アイテムシステムの統合テスト"""
    
    def test_consumable_item_with_status_effects(self):
        """状態異常付き消費アイテムのテスト"""
        status_effect = StatusEffect(StatusEffectType.POISON, 3, 10)
        item_effect = ItemEffect(
            hp_change=50,
            temporary_effects=[status_effect]
        )
        item = ConsumableItem("poison_potion", "毒薬", item_effect)
        
        assert item.effect.hp_change == 50
        assert len(item.effect.temporary_effects) == 1
        assert item.effect.temporary_effects[0].effect == StatusEffectType.POISON
    
    def test_weapon_with_complex_effects(self):
        """複雑な効果付き武器のテスト"""
        status_effect = StatusEffect(StatusEffectType.PARALYSIS, 2, 0)
        weapon_effect = WeaponEffect(
            attack_bonus=25,
            element=Element.THUNDER,
            element_damage=30,
            effective_races={Race.UNDEAD},
            status_effects={StatusEffectType.PARALYSIS: status_effect},
            status_chance=0.4,
            critical_rate_bonus=0.2
        )
        weapon = Weapon("thunder_sword", "雷の剣", WeaponType.SWORD, weapon_effect)
        
        # 基本ダメージ計算
        damage = weapon.calculate_damage(40)
        assert damage == 95  # 40 + 25 + 30
        
        # 種族特攻ダメージ計算
        damage = weapon.calculate_damage(40, Race.UNDEAD)
        assert damage == 127  # (40 + 25) * 1.5 + 30 = 97.5 + 30 = 127.5 (切り捨て)
        
        # クリティカル率
        assert weapon.get_critical_rate() == 0.2
    
    def test_armor_with_complex_effects(self):
        """複雑な効果付き防具のテスト"""
        armor_effect = ArmorEffect(
            defense_bonus=30,
            counter_damage=50,
            counter_chance=0.25,
            status_resistance={
                StatusEffectType.POISON: 0.8,
                StatusEffectType.PARALYSIS: 0.6
            },
            damage_reduction={
                DamageType.MAGICAL: 0.5,
                DamageType.PHYSICAL: 0.2
            },
            evasion_bonus=0.15,
            speed_bonus=8
        )
        armor = Armor("legendary_armor", "伝説の鎧", ArmorType.CHEST, armor_effect)
        
        assert armor.calculate_defense_bonus() == 30
        assert armor.get_counter_chance() == 0.25
        assert armor.get_counter_damage() == 50
        assert armor.get_status_resistance(StatusEffectType.POISON) == 0.8
        assert armor.get_damage_reduction(DamageType.MAGICAL) == 0.5
        assert armor.get_evasion_bonus() == 0.15
        assert armor.get_speed_bonus() == 8 