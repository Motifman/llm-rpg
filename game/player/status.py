from typing import Dict
from game.item.item_effect import ItemEffect
from dataclasses import dataclass
from game.enums import StatusEffectType


@dataclass
class StatusEffect:
    effect: StatusEffectType
    duration: int 
    value: int = 0
    
    def __str__(self):
        return f"{self.effect.value}({self.duration}ターン)" 


class Status:
    def __init__(self):
        self.hp = 100
        self.mp = 100
        self.attack = 10
        self.defense = 10
        self.speed = 10
        self.critical_rate = 0.0
        self.evasion_rate = 0.0
        self.experience_points = 0
        self.money = 0
        self.status_effects: Dict[StatusEffectType, StatusEffect] = {}

        self.max_hp = 100
        self.max_mp = 100
    
    def get_hp(self) -> int:
        return self.hp
    
    def get_max_hp(self) -> int:
        return self.max_hp
    
    def set_max_hp(self, max_hp: int):
        self.max_hp = max(0, max_hp)
        self.hp = min(self.hp, self.max_hp)

    def set_hp(self, hp: int):
        self.hp = max(0, min(hp, self.max_hp))
    
    def add_hp(self, hp: int):
        self.hp = max(0, min(self.hp + hp, self.max_hp))

    def get_mp(self) -> int:
        return self.mp
    
    def get_max_mp(self) -> int:
        return self.max_mp
    
    def set_max_mp(self, max_mp: int):
        self.max_mp = max(0, max_mp)
        self.mp = min(self.mp, self.max_mp)
    
    def set_mp(self, mp: int):
        self.mp = max(0, min(mp, self.max_mp))
    
    def add_mp(self, mp: int):
        self.mp = max(0, min(self.mp + mp, self.max_mp))
    
    def get_attack(self) -> int:
        return self.attack + self.get_attack_bonus()
    
    def set_attack(self, attack: int):
        self.attack = max(0, attack)
    
    def add_attack(self, attack: int):
        if attack < 0:
            attack = 0
        self.attack += attack
    
    def get_defense(self) -> int:
        return self.defense + self.get_defense_bonus()
    
    def set_defense(self, defense: int):
        self.defense = max(0, defense)
    
    def add_defense(self, defense: int):
        self.defense = max(0, self.defense + defense)
    
    def get_speed(self) -> int:
        return self.speed + self.get_speed_bonus()
    
    def set_speed(self, speed: int):
        self.speed = max(0, speed)
    
    def add_speed(self, speed: int):
        self.speed = max(0, self.speed + speed)
    
    def get_critical_rate(self) -> float:
        return self.critical_rate
    
    def set_critical_rate(self, critical_rate: float):
        self.critical_rate = max(0, critical_rate)
    
    def add_critical_rate(self, critical_rate: float):
        self.critical_rate = max(0, self.critical_rate + critical_rate)
    
    def get_evasion_rate(self) -> float:
        return self.evasion_rate
    
    def set_evasion_rate(self, evasion_rate: float):
        self.evasion_rate = max(0, evasion_rate)
    
    def add_evasion_rate(self, evasion_rate: float):
        self.evasion_rate = max(0, self.evasion_rate + evasion_rate)
    
    def get_experience_points(self) -> int:
        return self.experience_points
    
    def set_experience_points(self, experience_points: int):
        self.experience_points = max(0, experience_points)
    
    def add_experience_points(self, experience_points: int):
        self.experience_points = max(0, self.experience_points + experience_points)
    
    def get_money(self) -> int:
        return self.money
    
    def set_money(self, money: int):
        self.money = max(0, money)
    
    def add_money(self, money: int):
        self.money = max(0, self.money + money)
    
    def get_status_effects(self) -> Dict[StatusEffectType, StatusEffect]:
        return self.status_effects
    
    def set_status_effects(self, status_effects: Dict[StatusEffectType, StatusEffect]):
        self.status_effects = status_effects
    
    def add_status_effect(self, status_effect: StatusEffect):
        self.status_effects[status_effect.effect] = status_effect
    
    def remove_status_effect(self, status_effect: StatusEffect):
        self.status_effects.pop(status_effect.effect, None)
    
    def remove_status_effect_by_type(self, effect_type: StatusEffectType):
        self.status_effects.pop(effect_type, None)
    
    def has_status_effect(self, status_effect: StatusEffect) -> bool:
        return status_effect.effect in self.status_effects
    
    def has_status_effect_type(self, effect_type: StatusEffectType) -> bool:
        return effect_type in self.status_effects
    
    def get_status_effect(self, effect_type: StatusEffectType) -> StatusEffect:
        return self.status_effects.get(effect_type)
    
    def update_status_effect_duration(self, effect_type: StatusEffectType, new_duration: int):
        if effect_type in self.status_effects:
            self.status_effects[effect_type].duration = new_duration
    
    def _decrease_all_status_effect_durations(self):
        expired_effects = []
        for effect_type, effect in self.status_effects.items():
            effect.duration -= 1
            if effect.duration <= 0:
                expired_effects.append(effect_type)
        
        for effect_type in expired_effects:
            self.status_effects.pop(effect_type)
    
    def process_status_effects(self):
        for effect_type, effect in self.status_effects.items():
            if effect_type == StatusEffectType.POISON:
                self.add_hp(-effect.value)
            elif effect_type == StatusEffectType.BURN:
                self.add_hp(-effect.value)
        self._decrease_all_status_effect_durations()

    def get_attack_bonus(self) -> int:
        status_effect = self.status_effects.get(StatusEffectType.ATTACK_UP)
        return status_effect.value if status_effect else 0
    
    def get_defense_bonus(self) -> int:
        status_effect = self.status_effects.get(StatusEffectType.DEFENSE_UP)
        return status_effect.value if status_effect else 0
    
    def get_speed_bonus(self) -> int:
        status_effect = self.status_effects.get(StatusEffectType.SPEED_UP)
        return status_effect.value if status_effect else 0

    def is_alive(self) -> bool:
        return self.hp > 0
    
    def get_status_summary(self) -> str:
        return (f"HP: {self.hp}/{self.max_hp}, "
                f"MP: {self.mp}/{self.max_mp}, "
                f"攻撃: {self.attack}, 防御: {self.defense}, 素早さ: {self.speed}, "
                f"所持金: {self.money}, 経験値: {self.experience_points}, "
                f"クリティカル: {self.get_critical_rate():.1%}, 回避: {self.get_evasion_rate():.1%}")

    def apply_item_effect(self, effect: ItemEffect):
        self.add_hp(effect.hp_change)
        self.add_mp(effect.mp_change)
        self.add_money(effect.money_change)
        self.add_experience_points(effect.experience_change)
        for status_effect in effect.temporary_effects:
            self.add_status_effect(status_effect)

    def can_act(self) -> bool:
        if (self.has_status_effect_type(StatusEffectType.PARALYSIS) or 
            self.has_status_effect_type(StatusEffectType.SLEEP)):
            return False
        return self.is_alive()
    
    def is_confused(self) -> bool:
        return self.has_status_effect_type(StatusEffectType.CONFUSION)
    
    def is_silenced(self) -> bool:
        return self.has_status_effect_type(StatusEffectType.SILENCE)