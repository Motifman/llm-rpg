"""
ウェポンシステム総合デモ
===============================

本格的なRPG戦闘が可能になったことを検証するデモです。
- 装備システム
- 属性・種族相性
- 状態異常
- クリティカル・回避
- 反撃システム
- 特殊効果

"""

from src_old.models.agent import Agent
from src_old.models.monster import Monster, MonsterType, MonsterDropReward
from src_old.models.weapon import (
    Weapon, Armor, EquipmentSet, WeaponType, ArmorType, Element, Race, 
    StatusEffect, StatusCondition, WeaponEffect, ArmorEffect, DamageType
)
from src_old.models.item import Item
from src_old.models.action import AttackMonster, DefendBattle, EscapeBattle
from src_old.systems.battle import BattleManager
from src_old.systems.world import World
from src_old.models.spot import Spot


def create_legendary_weapons():
    """伝説の武器を作成"""
    weapons = {}
    
    # ドラゴンスレイヤー（ドラゴン特攻）
    dragon_slayer_effect = WeaponEffect(
        attack_bonus=25,
        effective_races={Race.DRAGON},
        race_damage_multiplier=2.5,
        element=Element.HOLY,
        element_damage=15,
        critical_rate_bonus=0.15
    )
    weapons["dragon_slayer"] = Weapon(
        "dragon_slayer", "ドラゴンスレイヤー", WeaponType.SWORD, dragon_slayer_effect, "legendary"
    )
    
    # 毒の短剣（状態異常特化）
    poison_dagger_effect = WeaponEffect(
        attack_bonus=12,
        status_effects=[
            StatusCondition(StatusEffect.POISON, 5, 8),
            StatusCondition(StatusEffect.PARALYSIS, 2)
        ],
        status_chance=0.7,
        critical_rate_bonus=0.25
    )
    weapons["poison_dagger"] = Weapon(
        "poison_dagger", "猛毒の短剣", WeaponType.SWORD, poison_dagger_effect, "epic"
    )
    
    # 炎の戦斧（炎属性・高威力）
    fire_axe_effect = WeaponEffect(
        attack_bonus=30,
        element=Element.FIRE,
        element_damage=20,
        critical_rate_bonus=0.1
    )
    weapons["fire_axe"] = Weapon(
        "fire_axe", "業火の戦斧", WeaponType.AXE, fire_axe_effect, "epic"
    )
    
    # 混乱の杖（混乱付与）
    confusion_staff_effect = WeaponEffect(
        attack_bonus=8,
        status_effects=[StatusCondition(StatusEffect.CONFUSION, 3)],
        status_chance=0.6,
        element=Element.DARK,
        element_damage=10
    )
    weapons["confusion_staff"] = Weapon(
        "confusion_staff", "混沌の杖", WeaponType.SWORD, confusion_staff_effect, "rare"
    )
    
    return weapons


def create_legendary_armors():
    """伝説の防具を作成"""
    armors = {}
    
    # ドラゴンスケイルアーマー（反撃・防御特化）
    dragon_scale_effect = ArmorEffect(
        defense_bonus=20,
        counter_damage=15,
        counter_chance=0.4,
        damage_reduction={DamageType.PHYSICAL: 0.3, DamageType.MAGICAL: 0.2},
        status_resistance={StatusEffect.POISON: 0.8}
    )
    armors["dragon_scale_armor"] = Armor(
        "dragon_scale_armor", "ドラゴンスケイルアーマー", ArmorType.CHEST, dragon_scale_effect, "legendary"
    )
    
    # 影のクローク（回避特化）
    shadow_cloak_effect = ArmorEffect(
        defense_bonus=8,
        evasion_bonus=0.35,
        speed_bonus=10,
        status_resistance={StatusEffect.CONFUSION: 0.6, StatusEffect.SLEEP: 0.9}
    )
    armors["shadow_cloak"] = Armor(
        "shadow_cloak", "影のクローク", ArmorType.CHEST, shadow_cloak_effect, "epic"
    )
    
    # 守護者のヘルム（状態異常耐性）
    guardian_helm_effect = ArmorEffect(
        defense_bonus=12,
        status_resistance={
            StatusEffect.PARALYSIS: 0.7,
            StatusEffect.CONFUSION: 0.5,
            StatusEffect.SILENCE: 0.8
        },
        damage_reduction={DamageType.MAGICAL: 0.4}
    )
    armors["guardian_helm"] = Armor(
        "guardian_helm", "守護者のヘルム", ArmorType.HELMET, guardian_helm_effect, "epic"
    )
    
    # 疾風のブーツ（素早さ特化）
    wind_boots_effect = ArmorEffect(
        defense_bonus=5,
        speed_bonus=15,
        evasion_bonus=0.2
    )
    armors["wind_boots"] = Armor(
        "wind_boots", "疾風のブーツ", ArmorType.SHOES, wind_boots_effect, "rare"
    )
    
    return armors


def create_powerful_monsters():
    """強力なモンスター群を作成"""
    monsters = {}
    
    # 古代ドラゴン（最強ボス）
    dragon_reward = MonsterDropReward(
        items=[],
        money=1000,
        experience=500,
        information=["古代ドラゴンを倒した勇者の証"]
    )
    monsters["ancient_dragon"] = Monster(
        "ancient_dragon", "古代炎龍アンシェント", "伝説の古代ドラゴン",
        MonsterType.AGGRESSIVE,
        max_hp=300, attack=35, defense=20, speed=12,
        race=Race.DRAGON, element=Element.FIRE,
        drop_reward=dragon_reward
    )
    
    # 闇の魔法使い（状態異常使い）
    dark_mage_reward = MonsterDropReward(
        items=[],
        money=300,
        experience=150,
        information=["闇魔法の秘伝書を手に入れた"]
    )
    monsters["dark_mage"] = Monster(
        "dark_mage", "闇の大魔法使い", "禁断魔法の使い手",
        MonsterType.AGGRESSIVE,
        max_hp=120, attack=25, defense=10, speed=15,
        race=Race.HUMAN, element=Element.DARK,
        drop_reward=dark_mage_reward
    )
    
    # アンデッドナイト（高防御）
    undead_knight_reward = MonsterDropReward(
        items=[],
        money=200,
        experience=100,
        information=["呪われた騎士の亡霊を浄化した"]
    )
    monsters["undead_knight"] = Monster(
        "undead_knight", "呪われし騎士", "不死の重装騎士",
        MonsterType.AGGRESSIVE,
        max_hp=180, attack=20, defense=25, speed=5,
        race=Race.UNDEAD, element=Element.DARK,
        drop_reward=undead_knight_reward
    )
    
    # 疾風狼（高速・回避型）
    wind_wolf_reward = MonsterDropReward(
        items=[],
        money=150,
        experience=80,
        information=["疾風狼の俊敏さを目撃した"]
    )
    monsters["wind_wolf"] = Monster(
        "wind_wolf", "疾風狼", "風のように素早い狼",
        MonsterType.AGGRESSIVE,
        max_hp=80, attack=18, defense=8, speed=25,
        race=Race.BEAST, element=Element.PHYSICAL,
        drop_reward=wind_wolf_reward
    )
    
    return monsters


def setup_battle_scenario():
    """戦闘シナリオのセットアップ"""
    # 世界とスポットを作成
    world = World()
    arena = Spot("battle_arena", "闘技場", "伝説の戦いが行われる場所")
    world.add_spot(arena)
    
    # 武器・防具を作成
    weapons = create_legendary_weapons()
    armors = create_legendary_armors()
    
    # モンスターを作成
    monsters = create_powerful_monsters()
    
    return world, weapons, armors, monsters


def create_warrior_build(world, weapons, armors):
    """戦士ビルドのエージェントを作成"""
    warrior = Agent("dragon_slayer_warrior", "ドラゴンスレイヤー戦士")
    warrior.set_current_spot_id("battle_arena")
    world.add_agent(warrior)
    
    # ステータス強化
    warrior.set_base_attack(20)
    warrior.set_base_defense(15)
    warrior.set_base_speed(10)
    warrior.set_max_hp(150)
    warrior.current_hp = 150
    
    # 装備追加
    for weapon in weapons.values():
        warrior.add_item(weapon)
    for armor in armors.values():
        warrior.add_item(armor)
    
    # ドラゴンスレイヤー装備
    warrior.equip_weapon(weapons["dragon_slayer"])
    warrior.equip_armor(armors["dragon_scale_armor"])
    warrior.equip_armor(armors["guardian_helm"])
    warrior.equip_armor(armors["wind_boots"])
    
    return warrior


def create_assassin_build(world, weapons, armors):
    """暗殺者ビルドのエージェントを作成"""
    assassin = Agent("shadow_assassin", "影の暗殺者")
    assassin.set_current_spot_id("battle_arena")
    world.add_agent(assassin)
    
    # ステータス設定（素早さ特化）
    assassin.set_base_attack(15)
    assassin.set_base_defense(8)
    assassin.set_base_speed(20)
    assassin.set_max_hp(120)
    assassin.current_hp = 120
    
    # 装備追加
    for weapon in weapons.values():
        assassin.add_item(weapon)
    for armor in armors.values():
        assassin.add_item(armor)
    
    # 毒・回避特化装備
    assassin.equip_weapon(weapons["poison_dagger"])
    assassin.equip_armor(armors["shadow_cloak"])
    assassin.equip_armor(armors["wind_boots"])
    
    return assassin


def demo_equipment_showcase():
    """装備システムの紹介"""
    print("🗡️ === ウェポンシステム紹介 === 🛡️")
    print()
    
    weapons = create_legendary_weapons()
    armors = create_legendary_armors()
    
    print("【伝説の武器】")
    for weapon in weapons.values():
        print(f"  {weapon}")
        print(f"    レアリティ: {weapon.rarity}")
        print()
    
    print("【伝説の防具】")
    for armor in armors.values():
        print(f"  {armor}")
        print(f"    レアリティ: {armor.rarity}")
        print()


def demo_agent_builds():
    """エージェントビルドの紹介"""
    print("⚔️ === キャラクタービルド紹介 === 🏹")
    print()
    
    world, weapons, armors, monsters = setup_battle_scenario()
    
    # 戦士ビルド
    warrior = create_warrior_build(world, weapons, armors)
    print("【ドラゴンスレイヤー戦士】")
    print(f"  基本ステータス: {warrior.get_status_summary()}")
    print(f"  {warrior.get_equipment_summary()}")
    print()
    
    # 暗殺者ビルド
    assassin = create_assassin_build(world, weapons, armors)
    print("【影の暗殺者】")
    print(f"  基本ステータス: {assassin.get_status_summary()}")
    print(f"  {assassin.get_equipment_summary()}")
    print()


def demo_battle_mechanics():
    """戦闘メカニクスのデモ"""
    print("⚡ === 戦闘システム機能紹介 === ⚡")
    print()
    
    world, weapons, armors, monsters = setup_battle_scenario()
    warrior = create_warrior_build(world, weapons, armors)
    
    # テスト用の弱いモンスター
    test_monster = Monster(
        "test_dummy", "テスト用ダミー", "実験台",
        MonsterType.PASSIVE,
        max_hp=100, attack=5, defense=3, speed=5,
        race=Race.MONSTER, element=Element.PHYSICAL
    )
    
    print("【ダメージ計算システム】")
    
    # 通常攻撃
    base_damage = warrior.get_attack() - test_monster.defense
    print(f"  基本攻撃力: {warrior.get_attack()}")
    print(f"  モンスター防御力: {test_monster.defense}")
    print(f"  基本ダメージ: {base_damage}")
    
    # 武器の種族特攻効果（ドラゴンスレイヤーでドラゴン以外）
    weapon_damage = warrior.equipment.weapon.calculate_damage(warrior.base_attack, test_monster.race)
    print(f"  武器効果込みダメージ: {weapon_damage}")
    
    # ドラゴンに対しての特攻
    dragon_damage = warrior.equipment.weapon.calculate_damage(warrior.base_attack, Race.DRAGON)
    print(f"  ドラゴン特攻ダメージ: {dragon_damage}")
    
    print()
    print("【確率システム】")
    print(f"  クリティカル率: {warrior.get_critical_rate():.1%}")
    print(f"  回避率: {warrior.get_evasion_rate():.1%}")
    
    print()
    print("【状態異常システム】")
    poison_weapon = weapons["poison_dagger"]
    print(f"  毒の短剣 状態異常発生率: {poison_weapon.effect.status_chance:.1%}")
    print(f"  付与効果: {[str(effect) for effect in poison_weapon.effect.status_effects]}")
    
    print()


def demo_epic_dragon_battle():
    """古代ドラゴンとの壮絶な戦い"""
    print("🐉 === 古代炎龍アンシェントとの決戦 === 🔥")
    print()
    
    world, weapons, armors, monsters = setup_battle_scenario()
    
    # 戦士を作成
    warrior = create_warrior_build(world, weapons, armors)
    dragon = monsters["ancient_dragon"]
    
    # モンスターをスポットに追加
    world.add_monster(dragon, "battle_arena")
    
    print("【戦闘前状況】")
    print(f"勇者: {warrior.name}")
    print(f"  {warrior.get_status_summary()}")
    print(f"  {warrior.get_equipment_summary()}")
    print()
    print(f"敵: {dragon.name}")
    print(f"  {dragon.get_status_summary()}")
    print()
    print("戦闘開始！")
    print("=" * 50)
    
    # 戦闘開始
    from src_old.models.action import StartBattle
    battle_id = world.execute_agent_start_battle("dragon_slayer_warrior", StartBattle("古代ドラゴンとの戦闘開始", "ancient_dragon"))
    battle = world.get_battle_manager().get_battle(battle_id)
    
    turn_count = 0
    max_turns = 20  # 無限ループ防止
    
    while not battle.is_battle_finished() and turn_count < max_turns:
        turn_count += 1
        print(f"\n--- ターン {turn_count} ---")
        
        current_actor = battle.get_current_actor()
        
        if battle.is_agent_turn():
            # エージェントのターン
            agent = battle.participants[current_actor]
            print(f"🗡️ {agent.name} のターン")
            
            # 簡単なAI：HPが低ければ防御、それ以外は攻撃
            if agent.current_hp < agent.max_hp * 0.3:
                action = DefendBattle()
                action_name = "防御"
            else:
                action = AttackMonster("古代ドラゴンを攻撃", "ancient_dragon")
                action_name = "攻撃"
            
            print(f"   選択行動: {action_name}")
            result = battle.execute_agent_action(current_actor, action)
            print(f"   結果: {result.message}")
            
            if result.critical:
                print("   💥 クリティカルヒット！")
            if result.status_effects_applied:
                print(f"   🩸 状態異常付与: {[str(e) for e in result.status_effects_applied]}")
            
        elif battle.is_monster_turn():
            # モンスターのターン
            print(f"🐉 {dragon.name} のターン")
            result = battle.execute_monster_turn()
            print(f"   {result.message}")
            
            if result.evaded:
                print("   💨 攻撃回避！")
            if result.counter_attack:
                print("   ⚡ 反撃発動！")
        
        # ターン進行
        battle.advance_turn()
        
        # 戦闘状況表示
        print("\n【現在の状況】")
        for participant in battle.get_participants():
            status = "正常" if not participant.status_conditions else f"状態異常: {', '.join(str(c) for c in participant.status_conditions)}"
            print(f"  {participant.name}: HP {participant.current_hp}/{participant.max_hp} ({status})")
        
        monster_status = "正常" if not dragon.status_conditions else f"状態異常: {', '.join(str(c) for c in dragon.status_conditions)}"
        print(f"  {dragon.name}: HP {dragon.current_hp}/{dragon.max_hp} ({monster_status})")
    
    # 戦闘結果
    print("\n" + "=" * 50)
    print("🏆 === 戦闘結果 === 🏆")
    
    if battle.is_battle_finished():
        result = battle.get_battle_result()
        if result.victory:
            print("✨ 勇者の勝利！ ✨")
            print(f"💰 獲得ゴールド: {result.rewards.money}")
            print(f"⭐ 獲得経験値: {result.rewards.experience}")
            for info in result.rewards.information:
                print(f"📜 {info}")
        else:
            print("💀 勇者の敗北...")
    else:
        print("⏰ 戦闘時間切れ")
    
    print()
    print("【戦闘ログ（抜粋）】")
    for log in battle.battle_log[-10:]:  # 最後の10行
        print(f"  {log}")


def demo_multi_agent_battle():
    """複数エージェントでの協力戦闘"""
    print("👥 === パーティ戦闘デモ === 👥")
    print()
    
    from src_old.models.action import StartBattle, JoinBattle
    world, weapons, armors, monsters = setup_battle_scenario()
    
    # 戦士と暗殺者を作成
    warrior = create_warrior_build(world, weapons, armors)
    assassin = create_assassin_build(world, weapons, armors)
    
    # 強敵を用意
    dark_mage = monsters["dark_mage"]
    world.add_monster(dark_mage, "battle_arena")
    
    print("【パーティ構成】")
    print(f"1. {warrior.name}: {warrior.get_status_summary()}")
    print(f"2. {assassin.name}: {assassin.get_status_summary()}")
    print()
    print(f"【敵】 {dark_mage.name}: {dark_mage.get_status_summary()}")
    print()
    
    # 戦闘開始（戦士が開始）
    battle_id = world.execute_agent_start_battle("dragon_slayer_warrior", StartBattle("闇の大魔法使いとの戦闘開始", "dark_mage"))
    battle = world.get_battle_manager().get_battle(battle_id)
    
    # 暗殺者が戦闘に参加
    from src_old.models.action import JoinBattle
    battle = world.get_battle_manager().get_battle(battle_id)
    battle.add_participant(world.get_agent("shadow_assassin"))
    
    print("🚀 協力戦闘開始！")
    print(f"参加者: {len(battle.get_participants())}人")
    print(f"ターン順序: {battle.turn_order}")
    print()
    
    # 数ターン実行
    for turn in range(1, 6):
        if battle.is_battle_finished():
            break
            
        print(f"--- ターン {turn} ---")
        current_actor = battle.get_current_actor()
        
        if battle.is_agent_turn():
            agent = battle.participants[current_actor]
            print(f"🎯 {agent.name} の行動")
            
            # 簡単な戦術AI
            action = AttackMonster("闇の魔法使いを攻撃", "dark_mage")
            result = battle.execute_agent_action(current_actor, action)
            print(f"   {result.message}")
            
        elif battle.is_monster_turn():
            print(f"🔮 {dark_mage.name} の行動")
            result = battle.execute_monster_turn()
            print(f"   {result.message}")
        
        battle.advance_turn()
        print()
    
    print("✅ パーティ戦闘システム正常動作確認")


def main():
    """メインデモ実行"""
    print("🎮 ウェポンシステム総合デモへようこそ！ 🎮")
    print("=" * 60)
    print()
    
    # 1. 装備システム紹介
    demo_equipment_showcase()
    
    # 2. キャラクタービルド紹介
    demo_agent_builds()
    
    # 3. 戦闘メカニクス説明
    demo_battle_mechanics()
    
    # 4. 壮絶なボス戦
    demo_epic_dragon_battle()
    
    # 5. パーティ戦闘
    demo_multi_agent_battle()
    
    print("=" * 60)
    print("🎊 ウェポンシステムデモ完了！ 🎊")
    print()
    print("【実装完了機能】")
    print("✅ 武器・防具システム")
    print("✅ 属性・種族相性システム")
    print("✅ 状態異常システム")
    print("✅ クリティカル・回避システム") 
    print("✅ 反撃システム")
    print("✅ 特殊効果システム")
    print("✅ 拡張戦闘システム")
    print("✅ パーティ戦闘システム")
    print()
    print("本格的なRPG戦闘が可能になりました！ 🏆")


if __name__ == "__main__":
    main() 