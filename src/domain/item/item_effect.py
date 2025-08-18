from dataclasses import dataclass, field
from typing import List
from src.domain.battle.battle_enum import StatusEffectType


@dataclass(frozen=True)
class ItemEffect:
    hp_delta: int = 0
    mp_delta: int = 0
    gold_delta: int = 0
    exp_delta: int = 0
    status_effects: List[StatusEffectType] = field(default_factory=list)
    
    def __post_init__(self):
        if self.status_effects is None:
            self.status_effects = []
    
    def get_effect_summary(self) -> str:
        effects: List[str] = []
        if self.hp_delta != 0:
            effects.append(f"HP{self.hp_delta:+d}")
        if self.mp_delta != 0:
            effects.append(f"MP{self.mp_delta:+d}")
        if self.gold_delta != 0:
            effects.append(f"所持金{self.gold_delta:+d}")
        if self.exp_delta != 0:
            effects.append(f"経験値{self.exp_delta:+d}")
        if self.status_effects:
            for effect_type in self.status_effects:
                effects.append(f"{effect_type.value}")
        
        return "効果: " + ", ".join(effects) if effects else "効果なし"