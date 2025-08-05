from game.battle.battle_effects import (
    BattleEffect, BattleContext, EffectResult,
    RaceAdvantageEffect, ElementDamageEffect, 
    StatusEffectApplier, CounterAttackEffect, DamageReductionEffect
)
from game.battle.battle_stats import BattleStats, BattleStatsCalculator
from game.item.equipment_item import Weapon, WeaponEffect, Armor, ArmorEffect
from game.enums import (
    WeaponType, ArmorType, Element, Race, StatusEffectType, 
    DamageType, Role
)
from game.player.status import StatusEffect
from game.player.player import Player


def demo_basic_battle_effects():
    """BattleEffectの基本的な使い方デモ"""
    print("=== BattleEffect 基本デモ ===")
    
    # プレイヤーとモンスターを作成
    player = Player("player1", "勇者", Role.ADVENTURER)
    monster = Player("monster1", "ゴブリン", Role.ADVENTURER)
    monster.race = Race.BEAST
    
    # 武器を作成
    weapon_effect = WeaponEffect(
        attack_bonus=15,
        element=Element.FIRE,
        element_damage=10,
        effective_races={Race.BEAST},
        race_damage_multiplier=1.5,
        status_effects={
            StatusEffectType.POISON: StatusEffect(StatusEffectType.POISON, 3, 5)
        },
        status_chance=0.3,
        critical_rate_bonus=0.1
    )
    
    weapon = Weapon("fire_sword", "炎の剣", "炎属性の剣", WeaponType.SWORD, weapon_effect)
    player.inventory.add_item(weapon)
    player.equip_item("fire_sword")
    
    # 戦闘コンテキストを作成
    context = BattleContext(
        attacker=player,
        target=monster,
        weapon=weapon
    )
    
    # 各種BattleEffectを作成
    effects = [
        RaceAdvantageEffect(effective_races={Race.BEAST}, multiplier=1.5),
        ElementDamageEffect(Element.FIRE, 10),
        StatusEffectApplier(weapon_effect.status_effects, weapon_effect.status_chance)
    ]
    
    # 各効果を適用
    total_damage = 100  # 基本ダメージ
    messages = []
    
    for effect in effects:
        result = effect.calculate_effect(context)
        total_damage = int(total_damage * result.damage_modifier) + result.additional_damage
        
        if result.message:
            messages.append(result.message)
        
        print(f"効果: {effect.__class__.__name__}")
        print(f"  条件: {effect.get_trigger_condition()}")
        print(f"  結果: {result.message if result.message else '効果なし'}")
        print(f"  ダメージ修飾子: {result.damage_modifier}")
        print(f"  追加ダメージ: {result.additional_damage}")
        print()
    
    print(f"最終ダメージ: {total_damage}")
    print(f"メッセージ: {' / '.join(messages)}")


def demo_armor_effects():
    """防具効果のデモ"""
    print("\n=== 防具効果デモ ===")
    
    # プレイヤーとモンスターを作成
    player = Player("player1", "勇者", Role.ADVENTURER)
    monster = Player("monster1", "ドラゴン", Role.ADVENTURER)
    
    # 防具を作成
    armor_effect = ArmorEffect(
        defense_bonus=20,
        evasion_bonus=0.1,
        speed_bonus=5,
        counter_damage=15,
        counter_chance=0.25,
        status_resistance={
            StatusEffectType.POISON: 0.5,
            StatusEffectType.PARALYSIS: 0.3
        },
        damage_reduction={
            DamageType.PHYSICAL: 0.2,
            DamageType.MAGICAL: 0.3
        }
    )
    
    armor = Armor("dragon_armor", "ドラゴンアーマー", "強力な防具", ArmorType.CHEST, armor_effect)
    player.inventory.add_item(armor)
    player.equip_item("dragon_armor")
    
    # 武器を作成（攻撃側）
    weapon_effect = WeaponEffect(
        attack_bonus=25,
        element=Element.FIRE,
        element_damage=20
    )
    weapon = Weapon("fire_sword", "炎の剣", "炎属性の剣", WeaponType.SWORD, weapon_effect)
    monster.inventory.add_item(weapon)
    monster.equip_item("fire_sword")
    
    # 戦闘コンテキスト（モンスターが攻撃、プレイヤーが防御）
    context = BattleContext(
        attacker=monster,
        target=player,
        weapon=weapon
    )
    
    # 防具効果を適用
    armor_effects = [
        DamageReductionEffect(DamageType.PHYSICAL, 0.2),
        DamageReductionEffect(DamageType.MAGICAL, 0.3),
        CounterAttackEffect(15, 0.25)
    ]
    
    print("防具効果の適用:")
    for effect in armor_effects:
        result = effect.calculate_effect(context)
        print(f"  効果: {effect.__class__.__name__}")
        print(f"  条件: {effect.get_trigger_condition()}")
        print(f"  結果: {result.message if result.message else '効果なし'}")
        print(f"  ダメージ修飾子: {result.damage_modifier}")
        print(f"  反撃ダメージ: {result.counter_damage}")
        print()


def demo_custom_battle_effect():
    """カスタムBattleEffectの作成例"""
    print("\n=== カスタムBattleEffectデモ ===")
    
    class CriticalBoostEffect(BattleEffect):
        """クリティカル時の追加ダメージ効果"""
        
        def __init__(self, critical_damage_bonus: int = 20):
            self.critical_damage_bonus = critical_damage_bonus
        
        def calculate_effect(self, context: BattleContext) -> EffectResult:
            if context.is_critical:
                return EffectResult(
                    additional_damage=self.critical_damage_bonus,
                    message=f"クリティカル追加ダメージ: {self.critical_damage_bonus}"
                )
            return EffectResult()
        
        def get_trigger_condition(self) -> str:
            return "クリティカルヒット時"
    
    class ComboEffect(BattleEffect):
        """連続攻撃効果"""
        
        def __init__(self, combo_chance: float = 0.3, combo_damage: int = 10):
            self.combo_chance = combo_chance
            self.combo_damage = combo_damage
        
        def calculate_effect(self, context: BattleContext) -> EffectResult:
            import random
            if random.random() < self.combo_chance:
                return EffectResult(
                    additional_damage=self.combo_damage,
                    message=f"連続攻撃！追加ダメージ: {self.combo_damage}"
                )
            return EffectResult()
        
        def get_trigger_condition(self) -> str:
            return f"攻撃命中時({self.combo_chance:.1%}確率)"
    
    # カスタム効果の使用例
    player = Player("player1", "勇者", Role.ADVENTURER)
    monster = Player("monster1", "スライム", Role.ADVENTURER)
    
    weapon = Weapon("combo_sword", "連続剣", "連続攻撃の剣", WeaponType.SWORD, WeaponEffect())
    player.inventory.add_item(weapon)
    player.equip_item("combo_sword")
    
    context = BattleContext(
        attacker=player,
        target=monster,
        weapon=weapon,
        is_critical=True  # クリティカルヒット
    )
    
    custom_effects = [
        CriticalBoostEffect(25),
        ComboEffect(0.4, 15)
    ]
    
    print("カスタム効果の適用:")
    for effect in custom_effects:
        result = effect.calculate_effect(context)
        print(f"  効果: {effect.__class__.__name__}")
        print(f"  条件: {effect.get_trigger_condition()}")
        print(f"  結果: {result.message if result.message else '効果なし'}")
        print(f"  追加ダメージ: {result.additional_damage}")
        print()


def demo_effect_chain():
    """効果の連鎖デモ"""
    print("\n=== 効果連鎖デモ ===")
    
    class ChainReactionEffect(BattleEffect):
        """連鎖反応効果"""
        
        def __init__(self, chain_count: int = 0):
            self.chain_count = chain_count
        
        def calculate_effect(self, context: BattleContext) -> EffectResult:
            # 連鎖回数に応じてダメージが増加
            chain_bonus = self.chain_count * 5
            return EffectResult(
                additional_damage=chain_bonus,
                message=f"連鎖反応！(連鎖{self.chain_count}回) 追加ダメージ: {chain_bonus}"
            )
        
        def get_trigger_condition(self) -> str:
            return f"連鎖{self.chain_count}回目"
    
    # 連鎖効果のシミュレーション
    base_damage = 100
    chain_effects = [
        ChainReactionEffect(1),
        ChainReactionEffect(2),
        ChainReactionEffect(3)
    ]
    
    print("連鎖効果のシミュレーション:")
    total_damage = base_damage
    for effect in chain_effects:
        result = effect.calculate_effect(None)  # コンテキストは使用しない
        total_damage += result.additional_damage
        print(f"  {result.message}")
        print(f"  累積ダメージ: {total_damage}")
        print()


if __name__ == "__main__":
    demo_basic_battle_effects()
    demo_armor_effects()
    demo_custom_battle_effect()
    demo_effect_chain() 