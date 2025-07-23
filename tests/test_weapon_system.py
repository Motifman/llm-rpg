import pytest
from src.models.agent import Agent
from src.models.monster import Monster, MonsterType, MonsterDropReward
from src.models.weapon import (
    Weapon, Armor, EquipmentSet, WeaponType, ArmorType, Element, Race, 
    StatusEffect, StatusCondition, WeaponEffect, ArmorEffect, DamageType
)
from src.models.item import Item
from src.systems.battle import BattleManager


class TestWeaponSystem:
    """ウェポンシステムのテスト"""
    
    def test_weapon_creation(self):
        """武器作成のテスト"""
        # 基本的な剣を作成
        sword_effect = WeaponEffect(
            attack_bonus=15,
            element=Element.FIRE,
            element_damage=5,
            critical_rate_bonus=0.1
        )
        
        sword = Weapon(
            item_id="fire_sword",
            description="炎の剣",
            weapon_type=WeaponType.SWORD,
            effect=sword_effect
        )
        
        assert sword.item_id == "fire_sword"
        assert sword.weapon_type == WeaponType.SWORD
        assert sword.effect.attack_bonus == 15
        assert sword.effect.element == Element.FIRE
        assert sword.get_critical_rate() == 0.1
    
    def test_armor_creation(self):
        """防具作成のテスト"""
        armor_effect = ArmorEffect(
            defense_bonus=10,
            counter_damage=5,
            counter_chance=0.2,
            evasion_bonus=0.1
        )
        
        armor = Armor(
            item_id="steel_armor",
            description="鋼の鎧",
            armor_type=ArmorType.ARMOR,
            effect=armor_effect
        )
        
        assert armor.item_id == "steel_armor"
        assert armor.armor_type == ArmorType.ARMOR
        assert armor.effect.defense_bonus == 10
        assert armor.get_counter_chance() == 0.2
        assert armor.get_evasion_bonus() == 0.1
    
    def test_equipment_set(self):
        """装備セットのテスト"""
        # 武器作成
        sword_effect = WeaponEffect(attack_bonus=10, critical_rate_bonus=0.05)
        sword = Weapon("sword", "剣", WeaponType.SWORD, sword_effect)
        
        # 防具作成
        helmet_effect = ArmorEffect(defense_bonus=5, evasion_bonus=0.05)
        helmet = Armor("helmet", "ヘルメット", ArmorType.HELMET, helmet_effect)
        
        armor_effect = ArmorEffect(defense_bonus=15, speed_bonus=2)
        armor = Armor("armor", "鎧", ArmorType.ARMOR, armor_effect)
        
        # 装備セット
        equipment = EquipmentSet()
        equipment.equip_weapon(sword)
        equipment.equip_armor(helmet)
        equipment.equip_armor(armor)
        
        assert equipment.get_total_attack_bonus() == 10
        assert equipment.get_total_defense_bonus() == 20
        assert equipment.get_total_speed_bonus() == 2
        assert equipment.get_total_critical_rate() == 0.05
        assert equipment.get_total_evasion_rate() == 0.05
    
    def test_agent_equipment_integration(self):
        """エージェントと装備システムの統合テスト"""
        agent = Agent("test_agent", "テストエージェント")
        
        # 武器を作成してインベントリに追加
        sword_effect = WeaponEffect(attack_bonus=20)
        sword = Weapon("power_sword", "力の剣", WeaponType.SWORD, sword_effect)
        agent.add_item(sword)
        
        # 防具を作成してインベントリに追加
        armor_effect = ArmorEffect(defense_bonus=10)
        armor = Armor("steel_armor", "鋼の鎧", ArmorType.ARMOR, armor_effect)
        agent.add_item(armor)
        
        # ベースステータス確認
        assert agent.base_attack == 10
        assert agent.base_defense == 5
        assert agent.attack == 10  # 装備なしなのでベース値
        assert agent.defense == 5
        
        # 武器装備
        assert agent.equip_weapon(sword) == True
        assert agent.attack == 30  # 10 + 20
        assert agent.has_item("power_sword") == False  # インベントリから削除
        
        # 防具装備
        assert agent.equip_armor(armor) == True
        assert agent.defense == 15  # 5 + 10
        assert agent.has_item("steel_armor") == False
        
        # 装備解除
        assert agent.unequip_weapon() == True
        assert agent.attack == 10  # ベース値に戻る
        assert agent.has_item("power_sword") == True  # インベントリに戻る
    
    def test_status_effects(self):
        """状態異常システムのテスト"""
        agent = Agent("test_agent", "テスト")
        
        # 毒状態を追加
        poison_condition = StatusCondition(StatusEffect.POISON, duration=3, value=5)
        agent.add_status_condition(poison_condition)
        
        assert agent.has_status_condition(StatusEffect.POISON) == True
        assert len(agent.status_conditions) == 1
        
        # 初期HP
        initial_hp = agent.current_hp
        
        # 状態異常処理（1ターン目）
        agent.process_status_effects()
        assert agent.current_hp == initial_hp - 5  # 毒ダメージ
        assert agent.status_conditions[0].duration == 2  # ターン数減少
        
        # 状態異常処理（2ターン目）
        agent.process_status_effects()
        assert agent.current_hp == initial_hp - 10
        assert agent.status_conditions[0].duration == 1
        
        # 状態異常処理（3ターン目）
        agent.process_status_effects()
        assert agent.current_hp == initial_hp - 15
        assert len(agent.status_conditions) == 0  # 効果終了
        assert agent.has_status_condition(StatusEffect.POISON) == False
    
    def test_monster_with_race_and_element(self):
        """種族・属性を持つモンスターのテスト"""
        # ドラゴン種族、炎属性のモンスター
        monster = Monster(
            monster_id="fire_dragon",
            name="炎のドラゴン",
            description="強力な炎のドラゴン",
            monster_type=MonsterType.AGGRESSIVE,
            max_hp=200,
            attack=25,
            defense=15,
            speed=10,
            race=Race.DRAGON,
            element=Element.FIRE
        )
        
        assert monster.race == Race.DRAGON
        assert monster.element == Element.FIRE
        assert "種族: dragon" in monster.get_status_summary()
        assert "属性: fire" in monster.get_status_summary()
    
    def test_weapon_damage_calculation(self):
        """武器ダメージ計算のテスト"""
        # ドラゴン特攻武器を作成
        dragon_slayer_effect = WeaponEffect(
            attack_bonus=20,
            effective_races={Race.DRAGON},
            race_damage_multiplier=2.0,
            element=Element.HOLY,
            element_damage=10
        )
        
        dragon_slayer = Weapon(
            "dragon_slayer",
            "ドラゴンスレイヤー",
            WeaponType.SWORD,
            dragon_slayer_effect
        )
        
        # 通常モンスターへのダメージ
        normal_damage = dragon_slayer.calculate_damage(10, Race.MONSTER)
        assert normal_damage == 40  # 10 + 20 + 10 (聖属性ダメージ)
        
        # ドラゴンへのダメージ（特攻効果）
        dragon_damage = dragon_slayer.calculate_damage(10, Race.DRAGON)
        assert dragon_damage == 70  # (10 + 20) * 2.0 + 10
    
    def test_armor_damage_reduction(self):
        """防具ダメージ軽減のテスト"""
        magic_resistance_effect = ArmorEffect(
            defense_bonus=5,
            damage_reduction={DamageType.MAGICAL: 0.3}  # 魔法ダメージ30%軽減
        )
        
        magic_cloak = Armor(
            "magic_cloak",
            "魔法のマント",
            ArmorType.ARMOR,
            magic_resistance_effect
        )
        
        assert magic_cloak.get_damage_reduction(DamageType.MAGICAL) == 0.3
        assert magic_cloak.get_damage_reduction(DamageType.PHYSICAL) == 0.0


class TestBattleSystemIntegration:
    """戦闘システム統合テスト"""
    
    def setup_method(self):
        """テストセットアップ"""
        self.agent = Agent("warrior", "戦士")
        self.monster = Monster(
            "goblin", "ゴブリン", "小さなモンスター",
            MonsterType.AGGRESSIVE,
            max_hp=50, attack=12, defense=5, speed=6,
            race=Race.MONSTER, element=Element.PHYSICAL
        )
        self.battle_manager = BattleManager()
    
    def test_equipped_weapon_in_battle(self):
        """装備武器での戦闘テスト"""
        # 強力な剣を装備
        sword_effect = WeaponEffect(
            attack_bonus=15,
            critical_rate_bonus=0.5,  # 50%クリティカル率
            status_effects=[StatusCondition(StatusEffect.POISON, 3, 5)],
            status_chance=1.0  # 100%状態異常付与
        )
        sword = Weapon("poison_sword", "毒の剣", WeaponType.SWORD, sword_effect)
        
        self.agent.add_item(sword)
        self.agent.equip_weapon(sword)
        
        # 装備ボーナス確認
        assert self.agent.attack == 25  # 10 + 15
        assert self.agent.get_critical_rate() == 0.55  # 0.05 + 0.5
        
        # 戦闘開始
        battle_id = self.battle_manager.start_battle("test_spot", self.monster, self.agent)
        battle = self.battle_manager.get_battle(battle_id)
        
        # 攻撃実行（回避を考慮して複数回試行）
        from src.models.action import AttackMonster
        attack_action = AttackMonster("ゴブリンを攻撃", "goblin")
        
        # 回避される可能性があるため、最大10回まで攻撃を試行
        successful_attack = False
        damage_dealt = 0
        
        for attempt in range(10):
            # 戦闘をリセットして再開
            if attempt > 0:
                self.setup_method()  # テストセットアップをやり直し
                self.agent.add_item(sword)
                self.agent.equip_weapon(sword)
                battle_id = self.battle_manager.start_battle("test_spot", self.monster, self.agent)
                battle = self.battle_manager.get_battle(battle_id)
            
            # 最初のターンは戦士なので攻撃可能
            result = battle.execute_agent_action("warrior", attack_action)
            
            if not result.evaded and result.damage > 0:
                successful_attack = True
                damage_dealt = result.damage
                print(f"攻撃成功（{attempt + 1}回目）: {result.message}")
                print(f"ダメージ: {damage_dealt}")
                print(f"モンスターHP: {self.monster.current_hp}/{self.monster.max_hp}")
                print(f"モンスター状態異常: {self.monster.status_conditions}")
                break
            else:
                print(f"攻撃失敗（{attempt + 1}回目）: {result.message}")
        
        # 10回試行しても成功しなかった場合はテスト失敗
        assert successful_attack, "10回攻撃を試行しても1回も成功しませんでした（回避率が異常に高い可能性があります）"
        
        # 攻撃が成功した場合の確認
        assert damage_dealt > 0, "攻撃は成功したがダメージが0です"
        
        # 毒状態異常が付与されているか確認（状態異常付与率100%）
        assert self.monster.has_status_condition(StatusEffect.POISON), "毒状態異常が付与されていません"
    
    def test_armor_effects_in_battle(self):
        """防具効果の戦闘テスト"""
        # 反撃防具を装備
        counter_armor_effect = ArmorEffect(
            defense_bonus=10,
            counter_damage=8,
            counter_chance=1.0,  # 100%反撃
            evasion_bonus=0.3    # 30%回避
        )
        counter_armor = Armor("counter_armor", "反撃の鎧", ArmorType.ARMOR, counter_armor_effect)
        
        self.agent.add_item(counter_armor)
        self.agent.equip_armor(counter_armor)
        
        # 防御力アップ確認
        assert self.agent.defense == 15  # 5 + 10
        assert self.agent.get_evasion_rate() == 0.35  # 0.05 + 0.3
        
        # 戦闘開始
        battle_id = self.battle_manager.start_battle("test_spot", self.monster, self.agent)
        battle = self.battle_manager.get_battle(battle_id)
        
        # モンスターの攻撃をシミュレート
        monster_action = battle._execute_monster_attack(self.agent)
        
        print(f"モンスター攻撃結果: {monster_action.message}")
        if monster_action.counter_attack:
            print("反撃が発動しました！")
        if monster_action.evaded:
            print("攻撃を回避しました！")


class TestAdvancedBattleFeatures:
    """高度な戦闘機能のテスト"""
    
    def test_status_effect_battle_flow(self):
        """状態異常を含む戦闘フローのテスト"""
        agent = Agent("mage", "魔法使い")
        monster = Monster(
            "orc", "オーク", "強いモンスター",
            MonsterType.AGGRESSIVE,
            max_hp=100, attack=15, defense=8, speed=5
        )
        
        # 麻痺武器を作成
        paralyze_staff_effect = WeaponEffect(
            attack_bonus=8,
            status_effects=[StatusCondition(StatusEffect.PARALYSIS, 2)],
            status_chance=1.0
        )
        paralyze_staff = Weapon("paralyze_staff", "麻痺の杖", WeaponType.SWORD, paralyze_staff_effect)
        
        agent.add_item(paralyze_staff)
        agent.equip_weapon(paralyze_staff)
        
        battle_manager = BattleManager()
        battle_id = battle_manager.start_battle("test_spot", monster, agent)
        battle = battle_manager.get_battle(battle_id)
        
        # 1ターン目：エージェントの攻撃（麻痺付与）
        from src.models.action import AttackMonster
        attack_action = AttackMonster("オークを攻撃", "orc")
        result = battle.execute_agent_action("mage", attack_action)
        
        # 麻痺が付与されたはず
        assert monster.has_status_condition(StatusEffect.PARALYSIS)
        print(f"麻痺付与成功: {result.message}")
        
        # ターン進行
        battle.advance_turn()
        
        # 2ターン目：モンスターのターン（麻痺で行動不可）
        monster_result = battle.execute_monster_turn()
        assert "行動できない" in monster_result.message
        print(f"モンスター行動不可: {monster_result.message}")
        
        # 状態異常の持続確認
        assert monster.status_conditions[0].duration == 1  # 2→1に減少
        
    def test_confusion_battle(self):
        """混乱状態の戦闘テスト"""
        agent = Agent("warrior", "戦士")
        
        # 混乱状態を付与
        confusion_condition = StatusCondition(StatusEffect.CONFUSION, 2)
        agent.add_status_condition(confusion_condition)
        
        monster = Monster("dummy", "ダミー", "テスト用", MonsterType.PASSIVE, max_hp=100)
        
        battle_manager = BattleManager()
        battle_id = battle_manager.start_battle("test_spot", monster, agent)
        battle = battle_manager.get_battle(battle_id)
        
        # 混乱時の攻撃（自分攻撃になるはず）
        from src.models.action import AttackMonster
        attack_action = AttackMonster("ダミーを攻撃", "dummy")
        
        initial_hp = agent.current_hp
        result = battle.execute_agent_action("warrior", attack_action)
        
        # 自分を攻撃したはず
        assert agent.current_hp < initial_hp
        assert "混乱" in result.message
        print(f"混乱攻撃: {result.message}")


if __name__ == "__main__":
    # 基本テスト実行
    weapon_test = TestWeaponSystem()
    
    print("=== ウェポンシステム基本テスト ===")
    weapon_test.test_weapon_creation()
    print("✅ 武器作成テスト完了")
    
    weapon_test.test_armor_creation()
    print("✅ 防具作成テスト完了")
    
    weapon_test.test_equipment_set()
    print("✅ 装備セットテスト完了")
    
    weapon_test.test_agent_equipment_integration()
    print("✅ エージェント装備統合テスト完了")
    
    weapon_test.test_status_effects()
    print("✅ 状態異常テスト完了")
    
    weapon_test.test_monster_with_race_and_element()
    print("✅ モンスター種族・属性テスト完了")
    
    weapon_test.test_weapon_damage_calculation()
    print("✅ 武器ダメージ計算テスト完了")
    
    weapon_test.test_armor_damage_reduction()
    print("✅ 防具ダメージ軽減テスト完了")
    
    print("\n=== 戦闘システム統合テスト ===")
    battle_test = TestBattleSystemIntegration()
    battle_test.setup_method()
    battle_test.test_equipped_weapon_in_battle()
    print("✅ 装備武器戦闘テスト完了")
    
    battle_test.setup_method()
    battle_test.test_armor_effects_in_battle()
    print("✅ 防具効果戦闘テスト完了")
    
    print("\n=== 高度戦闘機能テスト ===")
    advanced_test = TestAdvancedBattleFeatures()
    advanced_test.test_status_effect_battle_flow()
    print("✅ 状態異常戦闘フローテスト完了")
    
    advanced_test.test_confusion_battle()
    print("✅ 混乱戦闘テスト完了")
    
    print("\n🎉 すべてのウェポンシステムテストが完了しました！") 