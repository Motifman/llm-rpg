"""モンスター攻撃で確率付与する状態異常の宣言。"""

from dataclasses import dataclass

from ai_rpg_world.domain.combat.enum.combat_enum import StatusEffectType
from ai_rpg_world.domain.monster.exception.monster_exceptions import (
    MonsterTemplateValidationException,
)


@dataclass(frozen=True)
class AttackStatusEffectChance:
    """攻撃成功時に確率で付与する状態異常1件を表す。"""

    effect_type: StatusEffectType
    chance: float
    duration_ticks: int
    value: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.effect_type, StatusEffectType):
            raise MonsterTemplateValidationException(
                "attack status effect_type must be StatusEffectType"
            )
        if not isinstance(self.chance, (int, float)) or isinstance(
            self.chance, bool
        ):
            raise MonsterTemplateValidationException(
                "attack status effect chance must be numeric"
            )
        if not 0.0 <= float(self.chance) <= 1.0:
            raise MonsterTemplateValidationException(
                "attack status effect chance must be between 0.0 and 1.0"
            )
        if not isinstance(self.duration_ticks, int) or isinstance(
            self.duration_ticks, bool
        ):
            raise MonsterTemplateValidationException(
                "attack status effect duration_ticks must be int"
            )
        if self.duration_ticks <= 0:
            raise MonsterTemplateValidationException(
                "attack status effect duration_ticks must be greater than 0"
            )
        if not isinstance(self.value, (int, float)) or isinstance(self.value, bool):
            raise MonsterTemplateValidationException(
                "attack status effect value must be numeric"
            )

