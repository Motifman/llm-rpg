from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from game.item.item import UniqueItem
from game.enums import Element, Race, StatusEffectType, DamageType, WeaponType, ArmorType
from game.player.status import StatusEffect


@dataclass
class WeaponEffect:
    """武器効果"""
    attack_bonus: int = 0
    
    element: Optional[Element] = None
    element_damage: int = 0
    
    effective_races: Set[Race] = field(default_factory=set)
    race_damage_multiplier: float = 1.5 
    
    status_effects: Dict[StatusEffectType, StatusEffect] = field(default_factory=dict)
    status_chance: float = 0.0 
    
    critical_rate_bonus: float = 0.0 
    
    def __str__(self):
        effects = []
        if self.attack_bonus > 0:
            effects.append(f"攻撃力+{self.attack_bonus}")
        if self.element:
            effects.append(f"{self.element.value}属性+{self.element_damage}")
        if self.effective_races:
            races = [race.value for race in self.effective_races]
            effects.append(f"特攻: {', '.join(races)}")
        if self.status_effects:
            effects.append(f"状態異常: {', '.join(str(e) for e in self.status_effects.values())}")
        if self.critical_rate_bonus > 0:
            effects.append(f"クリティカル+{self.critical_rate_bonus:.1%}")
        
        return " / ".join(effects) if effects else "特殊効果なし"


class Weapon(UniqueItem):
    """武器アイテム"""
    
    def __init__(self, item_id: str, name: str, description: str, weapon_type: WeaponType, 
                 effect: WeaponEffect, rarity: str = "common", max_durability: int = 100):
        super().__init__(item_id, name, description)
        self.weapon_type = weapon_type
        self.effect = effect
        self.rarity = rarity
        self.max_durability = max_durability
        self.current_durability = max_durability
    
    def calculate_damage(self, base_attack: int, target_race: Optional[Race] = None) -> int:
        base_damage = base_attack + self.effect.attack_bonus
        
        if target_race and target_race in self.effect.effective_races:
            base_damage = int(base_damage * self.effect.race_damage_multiplier)
        
        total_damage = base_damage
        if self.effect.element and self.effect.element != Element.PHYSICAL:
            total_damage += self.effect.element_damage
        
        return total_damage
    
    def get_critical_rate(self) -> float:
        return self.effect.critical_rate_bonus
    
    def get_status_description(self) -> str:
        durability_percent = (self.current_durability / self.max_durability) * 100
        return f"{self.weapon_type.value} - 耐久度: {self.current_durability}/{self.max_durability} ({durability_percent:.0f}%)"
    
    def use_durability(self, amount: int = 1) -> bool:
        """耐久度を消費し、破損した場合はTrueを返す"""
        self.current_durability = max(0, self.current_durability - amount)
        return self.current_durability <= 0
    
    def repair(self, amount: int = None) -> int:
        """耐久度を回復し、回復した量を返す"""
        if amount is None:
            amount = self.max_durability - self.current_durability
        
        old_durability = self.current_durability
        self.current_durability = min(self.max_durability, self.current_durability + amount)
        return self.current_durability - old_durability
    
    def is_broken(self) -> bool:
        """破損しているかどうか"""
        return self.current_durability <= 0
    
    def can_be_traded(self) -> bool:
        """武器が取引可能かどうかを判定"""
        # 破損していない場合のみ取引可能
        return not self.is_broken()
    
    def __str__(self):
        return f"{self.name} ({self.weapon_type.value}) - {self.description} [{self.effect}]"


@dataclass
class ArmorEffect:
    """防具効果"""
    defense_bonus: int = 0
    counter_damage: int = 0
    counter_chance: float = 0.0 
    
    status_resistance: Dict[StatusEffect, float] = field(default_factory=dict) 
    damage_reduction: Dict[DamageType, float] = field(default_factory=dict) 

    evasion_bonus: float = 0.0 
    speed_bonus: int = 0 
    
    def __str__(self):
        effects = []
        if self.defense_bonus > 0:
            effects.append(f"防御力+{self.defense_bonus}")
        if self.counter_damage > 0:
            effects.append(f"反撃({self.counter_chance:.1%})")
        if self.status_resistance:
            resistances = [f"{k.value}耐性{v:.1%}" for k, v in self.status_resistance.items()]
            effects.append(f"耐性: {', '.join(resistances)}")
        if self.damage_reduction:
            reductions = [f"{k.value}軽減{v:.1%}" for k, v in self.damage_reduction.items()]
            effects.append(f"軽減: {', '.join(reductions)}")
        if self.evasion_bonus > 0:
            effects.append(f"回避+{self.evasion_bonus:.1%}")
        if self.speed_bonus > 0:
            effects.append(f"素早さ+{self.speed_bonus}")
        
        return " / ".join(effects) if effects else "特殊効果なし"


class Armor(UniqueItem):
    """防具アイテム"""
    
    def __init__(self, item_id: str, name: str, description: str, armor_type: ArmorType, 
                 effect: ArmorEffect, rarity: str = "common", max_durability: int = 100):
        super().__init__(item_id, name, description)
        self.armor_type = armor_type
        self.effect = effect
        self.rarity = rarity
        self.max_durability = max_durability
        self.current_durability = max_durability
    
    def calculate_defense_bonus(self) -> int:
        return self.effect.defense_bonus
    
    def get_damage_reduction(self, damage_type: DamageType) -> float:
        return self.effect.damage_reduction.get(damage_type, 0.0)
    
    def get_status_resistance(self, status_effect_type: StatusEffectType) -> float:
        return self.effect.status_resistance.get(status_effect_type, 0.0)
    
    def get_counter_chance(self) -> float:
        return self.effect.counter_chance
    
    def get_counter_damage(self) -> int:
        return self.effect.counter_damage
    
    def get_evasion_bonus(self) -> float:
        return self.effect.evasion_bonus
    
    def get_speed_bonus(self) -> int:
        return self.effect.speed_bonus
    
    def get_status_description(self) -> str:
        durability_percent = (self.current_durability / self.max_durability) * 100
        return f"{self.armor_type.value} - 耐久度: {self.current_durability}/{self.max_durability} ({durability_percent:.0f}%)"
    
    def use_durability(self, amount: int = 1) -> bool:
        """耐久度を消費し、破損した場合はTrueを返す"""
        self.current_durability = max(0, self.current_durability - amount)
        return self.current_durability <= 0
    
    def repair(self, amount: int = None) -> int:
        """耐久度を回復し、回復した量を返す"""
        if amount is None:
            amount = self.max_durability - self.current_durability
        
        old_durability = self.current_durability
        self.current_durability = min(self.max_durability, self.current_durability + amount)
        return self.current_durability - old_durability
    
    def is_broken(self) -> bool:
        """破損しているかどうか"""
        return self.current_durability <= 0
    
    def can_be_traded(self) -> bool:
        """防具が取引可能かどうかを判定"""
        # 破損していない場合のみ取引可能
        return not self.is_broken()
    
    def __str__(self):
        return f"{self.name} ({self.armor_type.value}) - {self.description} [{self.effect}]"
