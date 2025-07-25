from dataclasses import dataclass, field
from typing import List, TYPE_CHECKING

if TYPE_CHECKING:
    from game.player.status import StatusEffect


@dataclass(frozen=True)
class ItemEffect:
    hp_change: int = 0
    mp_change: int = 0
    money_change: int = 0
    experience_change: int = 0
    temporary_effects: List["StatusEffect"] = field(default_factory=list)
    
    def __str__(self):
        effects = []
        if self.hp_change != 0:
            effects.append(f"HP{self.hp_change:+d}")
        if self.mp_change != 0:
            effects.append(f"MP{self.mp_change:+d}")
        if self.money_change != 0:
            effects.append(f"所持金{self.money_change:+d}")
        if self.experience_change != 0:
            effects.append(f"経験値{self.experience_change:+d}")
        if self.temporary_effects:
            for effect in self.temporary_effects:
                effects.append(f"{effect.effect.value}: {effect.duration}ターン")
        
        return "効果: " + ", ".join(effects) if effects else "効果なし"
    
    def __repr__(self):
        return f"ItemEffect(hp_change={self.hp_change}, mp_change={self.mp_change}, money_change={self.money_change}, experience_change={self.experience_change}, temporary_effects={self.temporary_effects})" 