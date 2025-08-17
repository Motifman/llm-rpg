from dataclasses import dataclass, field
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from src.domain.battle.status_effect import StatusEffect


@dataclass(frozen=True)
class ItemEffect:
    hp_delta: int = 0
    mp_delta: int = 0
    gold_delta: int = 0
    exp_delta: int = 0
    temporary_effects: List["StatusEffect"] = field(default_factory=list)
    
    def __post_init__(self):
        if self.hp_delta < 0:
            raise ValueError(f"hp_delta must be >= 0. hp_delta: {self.hp_delta}")
        if self.mp_delta < 0:
            raise ValueError(f"mp_delta must be >= 0. mp_delta: {self.mp_delta}")
        if self.gold_delta < 0:
            raise ValueError(f"gold_delta must be >= 0. gold_delta: {self.gold_delta}")
        if self.exp_delta < 0:
            raise ValueError(f"exp_delta must be >= 0. exp_delta: {self.exp_delta}")
        if self.temporary_effects:
            for effect in self.temporary_effects:
                if effect.duration < 0:
                    raise ValueError(f"duration must be >= 0. duration: {effect.duration}")
        if self.temporary_effects is None:
            self.temporary_effects = []
    
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
        if self.temporary_effects:
            for effect in self.temporary_effects:
                effects.append(f"{effect.effect_type.value}: {effect.duration}ターン")
        
        return "効果: " + ", ".join(effects) if effects else "効果なし"