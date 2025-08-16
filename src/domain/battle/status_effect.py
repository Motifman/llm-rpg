from dataclasses import dataclass
from src.domain.battle.battle_enum import StatusEffectType


@dataclass
class StatusEffect:
    effect: StatusEffectType
    duration: int 
    value: int = 0
    
    def __str__(self):
        return f"{self.effect.value}({self.duration}ターン)" 