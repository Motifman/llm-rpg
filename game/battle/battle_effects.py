from abc import ABC, abstractmethod
from typing import List, Optional
from dataclasses import dataclass
from game.enums import StatusEffectType, Race, Element, DamageType
from game.player.status import StatusEffect


class BattleEffect(ABC):
    """戦闘時の動的効果を表すインターフェース"""
    
    @abstractmethod
    def calculate_effect(self, context: 'BattleContext') -> 'EffectResult':
        """効果を計算して結果を返す"""
        pass
    
    @abstractmethod
    def get_trigger_condition(self) -> str:
        """効果の発生条件を返す"""
        pass


@dataclass
class BattleContext:
    """戦闘コンテキスト"""
    attacker: 'Player'
    target: 'Player'
    is_critical: bool = False


@dataclass
class EffectResult:
    """効果の結果"""
    damage_modifier: float = 1.0
    additional_damage: int = 0
    status_effects: List[StatusEffect] = None
    counter_damage: int = 0
    message: str = ""
    
    def __post_init__(self):
        if self.status_effects is None:
            self.status_effects = []


class RaceAdvantageEffect(BattleEffect):
    """種族特攻効果"""
    
    def __init__(self, effective_races: set, multiplier: float = 1.5):
        self.effective_races = effective_races
        self.multiplier = multiplier
    
    def calculate_effect(self, context: BattleContext) -> EffectResult:
        if hasattr(context.target, 'race') and context.target.race in self.effective_races:
            return EffectResult(
                damage_modifier=self.multiplier,
                message=f"{context.target.race.value}特攻！"
            )
        return EffectResult()
    
    def get_trigger_condition(self) -> str:
        races = [race.value for race in self.effective_races]
        return f"対象が{', '.join(races)}の場合"


class ElementDamageEffect(BattleEffect):
    """属性ダメージ効果"""
    
    def __init__(self, element: Element, damage: int):
        self.element = element
        self.damage = damage
    
    def calculate_effect(self, context: BattleContext) -> EffectResult:
        if self.element != Element.PHYSICAL:
            return EffectResult(
                additional_damage=self.damage,
                message=f"{self.element.value}属性ダメージ"
            )
        return EffectResult()
    
    def get_trigger_condition(self) -> str:
        return f"{self.element.value}属性攻撃時"


class StatusEffectApplier(BattleEffect):
    """状態異常付与効果"""
    
    def __init__(self, status_effects: dict, chance: float):
        self.status_effects = status_effects
        self.chance = chance
    
    def calculate_effect(self, context: BattleContext) -> EffectResult:
        applied_effects = []
        
        for status_type, effect in self.status_effects.items():
            # 耐性判定
            bonuses = context.target.equipment.get_equipment_bonuses()
            resistance = bonuses['status_resistance'].get(status_type, 0.0)
            if self._check_resistance(resistance):
                continue
            
            # 付与確率判定
            if self._check_chance(self.chance):
                applied_effects.append(effect)
        
        if applied_effects:
            return EffectResult(
                status_effects=applied_effects,
                message=f"状態異常付与: {', '.join(str(e) for e in applied_effects)}"
            )
        return EffectResult()
    
    def get_trigger_condition(self) -> str:
        return f"攻撃命中時({self.chance:.1%}確率)"
    
    def _check_resistance(self, resistance: float) -> bool:
        import random
        return random.random() < resistance
    
    def _check_chance(self, chance: float) -> bool:
        import random
        return random.random() < chance


class CounterAttackEffect(BattleEffect):
    """反撃効果"""
    
    def __init__(self, damage: int, chance: float):
        self.damage = damage
        self.chance = chance
    
    def calculate_effect(self, context: BattleContext) -> EffectResult:
        if self._check_chance(self.chance):
            # 反撃ダメージも軽減される
            counter_damage = self.damage
            for armor in context.attacker.equipment.get_equipped_armors():
                if armor.is_broken():
                    continue
                counter_damage = armor.apply_damage_reduction(
                    counter_damage, DamageType.PHYSICAL
                )
            
            return EffectResult(
                counter_damage=counter_damage,
                message=f"反撃ダメージ: {counter_damage}"
            )
        return EffectResult()
    
    def get_trigger_condition(self) -> str:
        return f"被攻撃時({self.chance:.1%}確率)"
    
    def _check_chance(self, chance: float) -> bool:
        import random
        return random.random() < chance


class DamageReductionEffect(BattleEffect):
    """ダメージ軽減効果"""
    
    def __init__(self, damage_type: DamageType, reduction_rate: float):
        self.damage_type = damage_type
        self.reduction_rate = reduction_rate
    
    def calculate_effect(self, context: BattleContext) -> EffectResult:
        if self.damage_type == DamageType.PHYSICAL:
            return EffectResult(
                damage_modifier=1.0 - self.reduction_rate,
                message=f"{self.damage_type.value}ダメージ軽減({self.reduction_rate:.1%})"
            )
        return EffectResult()
    
    def get_trigger_condition(self) -> str:
        return f"{self.damage_type.value}ダメージ被攻撃時" 