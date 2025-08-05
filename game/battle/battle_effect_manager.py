from typing import List
from dataclasses import dataclass
from game.item.equipment_item import Weapon, Armor
from game.enums import Element, Race, StatusEffectType, DamageType
from game.battle.battle_effects import BattleEffect, BattleContext, RaceAdvantageEffect, ElementDamageEffect, StatusEffectApplier, CounterAttackEffect, DamageReductionEffect


class BattleEffectManager:
    """BattleEffectを管理し、戦闘時に適用するクラス"""
    
    def __init__(self):
        self.weapon_effects: List[BattleEffect] = []
        self.armor_effects: List[BattleEffect] = []
        self.special_effects: List[BattleEffect] = []
    
    def add_weapon_effect(self, effect: BattleEffect):
        """武器効果を追加"""
        self.weapon_effects.append(effect)
    
    def add_armor_effect(self, effect: BattleEffect):
        """防具効果を追加"""
        self.armor_effects.append(effect)
    
    def add_special_effect(self, effect: BattleEffect):
        """特殊効果を追加"""
        self.special_effects.append(effect)
    
    def create_weapon_effects_from_weapon(self, weapon: Weapon) -> List[BattleEffect]:
        """武器からBattleEffectを作成"""
        effects = []
        
        # 種族特攻効果
        if weapon.effect.effective_races:
            effects.append(
                RaceAdvantageEffect(
                    effective_races=weapon.effect.effective_races,
                    multiplier=weapon.effect.race_damage_multiplier
                )
            )
        
        # 属性ダメージ効果
        if weapon.effect.element and weapon.effect.element != Element.PHYSICAL:
            effects.append(
                ElementDamageEffect(
                    element=weapon.effect.element,
                    damage=weapon.effect.element_damage
                )
            )
        
        # 状態異常付与効果
        if weapon.effect.status_effects and weapon.effect.status_chance > 0:
            effects.append(
                StatusEffectApplier(
                    status_effects=weapon.effect.status_effects,
                    chance=weapon.effect.status_chance
                )
            )
        
        return effects
    
    def create_armor_effects_from_armor(self, armor: Armor) -> List[BattleEffect]:
        """防具からBattleEffectを作成"""
        effects = []
        
        # ダメージ軽減効果
        for damage_type, reduction_rate in armor.effect.damage_reduction.items():
            effects.append(
                DamageReductionEffect(
                    damage_type=damage_type,
                    reduction_rate=reduction_rate
                )
            )
        
        # 反撃効果
        if armor.effect.counter_damage > 0 and armor.effect.counter_chance > 0:
            effects.append(
                CounterAttackEffect(
                    damage=armor.effect.counter_damage,
                    chance=armor.effect.counter_chance
                )
            )
        
        return effects
    
    def apply_attack_effects(self, context: BattleContext, base_damage: int) -> 'AttackEffectResult':
        """攻撃時の効果を適用"""
        total_damage = base_damage
        applied_effects = []
        status_effects = []
        counter_damage = 0
        messages = []
        
        # 武器効果を適用
        for effect in self.weapon_effects:
            result = effect.calculate_effect(context)
            total_damage = int(total_damage * result.damage_modifier) + result.additional_damage
            applied_effects.append(effect)
            
            if result.message:
                messages.append(result.message)
            
            if result.status_effects:
                status_effects.extend(result.status_effects)
        
        # 特殊効果を適用
        for effect in self.special_effects:
            result = effect.calculate_effect(context)
            total_damage = int(total_damage * result.damage_modifier) + result.additional_damage
            applied_effects.append(effect)
            
            if result.message:
                messages.append(result.message)
            
            if result.status_effects:
                status_effects.extend(result.status_effects)
        
        return AttackEffectResult(
            final_damage=total_damage,
            applied_effects=applied_effects,
            status_effects=status_effects,
            counter_damage=counter_damage,
            messages=messages
        )
    
    def apply_defense_effects(self, context: BattleContext, base_damage: int) -> 'DefenseEffectResult':
        """防御時の効果を適用"""
        total_damage = base_damage
        applied_effects = []
        counter_damage = 0
        messages = []
        
        # 防具効果を適用
        for effect in self.armor_effects:
            result = effect.calculate_effect(context)
            total_damage = int(total_damage * result.damage_modifier)
            applied_effects.append(effect)
            
            if result.message:
                messages.append(result.message)
            
            if result.counter_damage > 0:
                counter_damage += result.counter_damage
        
        return DefenseEffectResult(
            final_damage=total_damage,
            applied_effects=applied_effects,
            counter_damage=counter_damage,
            messages=messages
        )
    
    def get_effect_summary(self) -> str:
        """効果の要約を取得"""
        summaries = []
        
        if self.weapon_effects:
            summaries.append(f"武器効果: {len(self.weapon_effects)}個")
        
        if self.armor_effects:
            summaries.append(f"防具効果: {len(self.armor_effects)}個")
        
        if self.special_effects:
            summaries.append(f"特殊効果: {len(self.special_effects)}個")
        
        return " / ".join(summaries) if summaries else "効果なし"


@dataclass
class AttackEffectResult:
    """攻撃効果の結果"""
    final_damage: int
    applied_effects: List[BattleEffect]
    status_effects: List
    counter_damage: int
    messages: List[str]


@dataclass
class DefenseEffectResult:
    """防御効果の結果"""
    final_damage: int
    applied_effects: List[BattleEffect]
    counter_damage: int
    messages: List[str]


# 使用例
def demo_battle_effect_manager():
    """BattleEffectManagerの使用例"""
    from game.item.equipment_item import Weapon, WeaponEffect, Armor, ArmorEffect
    from game.enums import WeaponType, ArmorType, Element, Race, StatusEffectType
    from game.player.status import StatusEffect
    from game.player.player import Player
    from game.enums import Role
    
    # プレイヤーとモンスターを作成
    player = Player("player1", "勇者", Role.WARRIOR)
    monster = Player("monster1", "ゴブリン", Role.MONSTER)
    monster.race = Race.GOBLIN
    
    # 武器を作成
    weapon_effect = WeaponEffect(
        attack_bonus=15,
        element=Element.FIRE,
        element_damage=10,
        effective_races={Race.GOBLIN},
        race_damage_multiplier=1.5,
        status_effects={
            StatusEffectType.BURN: StatusEffect(StatusEffectType.BURN, 3, 5)
        },
        status_chance=0.3
    )
    
    weapon = Weapon("fire_sword", "炎の剣", "炎属性の剣", WeaponType.SWORD, weapon_effect)
    player.inventory.add_item(weapon)
    player.equip_item("fire_sword")
    
    # 防具を作成
    armor_effect = ArmorEffect(
        defense_bonus=20,
        damage_reduction={DamageType.PHYSICAL: 0.2},
        counter_damage=10,
        counter_chance=0.25
    )
    
    armor = Armor("iron_armor", "鉄の鎧", "鉄製の鎧", ArmorType.CHEST, armor_effect)
    monster.inventory.add_item(armor)
    monster.equip_item("iron_armor")
    
    # BattleEffectManagerを作成
    manager = BattleEffectManager()
    
    # 武器効果を追加
    weapon_effects = manager.create_weapon_effects_from_weapon(weapon)
    for effect in weapon_effects:
        manager.add_weapon_effect(effect)
    
    # 防具効果を追加
    armor_effects = manager.create_armor_effects_from_armor(armor)
    for effect in armor_effects:
        manager.add_armor_effect(effect)
    
    # 攻撃コンテキスト
    attack_context = BattleContext(
        attacker=player,
        target=monster,
        weapon=weapon,
        base_damage=100
    )
    
    # 攻撃効果を適用
    attack_result = manager.apply_attack_effects(attack_context)
    print(f"攻撃結果: ダメージ{attack_result.final_damage}")
    print(f"メッセージ: {' / '.join(attack_result.messages)}")
    
    # 防御コンテキスト（モンスターが攻撃、プレイヤーが防御）
    defense_context = BattleContext(
        attacker=monster,
        target=player,
        weapon=weapon,
        base_damage=80
    )
    
    # 防御効果を適用
    defense_result = manager.apply_defense_effects(defense_context)
    print(f"防御結果: 最終ダメージ{defense_result.final_damage}")
    print(f"反撃ダメージ: {defense_result.counter_damage}")
    print(f"メッセージ: {' / '.join(defense_result.messages)}")
    
    print(f"効果要約: {manager.get_effect_summary()}")


if __name__ == "__main__":
    demo_battle_effect_manager() 