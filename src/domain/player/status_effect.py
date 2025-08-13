from dataclasses import dataclass
from domain.player.enum import StatusEffectType
 


@dataclass
class StatusEffect:
    """状態異常"""
    effect: StatusEffectType
    duration: int 
    value: int = 0
    
    def __str__(self):
        return f"{self.effect.value}({self.duration}ターン)" 