from dataclasses import dataclass
from ai_rpg_world.domain.combat.exception.combat_exceptions import DamageValidationException


@dataclass(frozen=True)
class Damage:
    """計算済みダメージ情報"""
    value: int
    is_critical: bool = False
    is_evaded: bool = False

    def __post_init__(self):
        if self.value < 0:
            raise DamageValidationException(f"Damage value cannot be negative: {self.value}")

    @classmethod
    def evaded(cls) -> "Damage":
        return cls(value=0, is_evaded=True)

    @classmethod
    def normal(cls, value: int, is_critical: bool = False) -> "Damage":
        return cls(value=value, is_critical=is_critical, is_evaded=False)
