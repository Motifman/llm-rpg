from dataclasses import dataclass
from domain.player.player_enum import StatusEffectType


@dataclass
class StatusEffectDto:
    status_effect_type: StatusEffectType
    message: str