from dataclasses import dataclass
from src.domain.battle.battle_enum import StatusEffectType


@dataclass
class StatusEffectResult:
    effect_type: StatusEffectType
    message: str
    damage_dealt: int = 0
    healing_done: int = 0