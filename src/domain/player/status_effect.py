from dataclasses import dataclass
from src.domain.player.player_enum import StatusEffectType
 


@dataclass
class StatusEffect:
    """状態異常"""
    effect: StatusEffectType
    duration: int 
    value: int = 0
    
    def __str__(self):
        return f"{self.effect.value}({self.duration}ターン)" 