from dataclasses import dataclass
from src.domain.battle.battle_enum import StatusEffectType


@dataclass
class StatusEffect:
    effect_type: StatusEffectType
    duration: int
    value: int = 0
    
    def __post_init__(self):
        if self.duration < 0:
            raise ValueError(f"duration must be >= 0. duration: {self.duration}")
        if self.effect_type is None:
            raise ValueError(f"effect_type must not be None. effect_type: {self.effect_type}")
        if self.value < 0:
            raise ValueError(f"value must be >= 0. value: {self.value}")
    
    def get_effect_summary(self) -> str:
        return f"{self.effect_type.value}({self.duration}ターン)" 