"""
Combatドメインの例外定義
"""

from ai_rpg_world.domain.common.exception import (
    DomainException,
    ValidationException,
)


class CombatDomainException(DomainException):
    """Combatドメインの基底例外"""

    domain = "combat"


class HitBoxValidationException(CombatDomainException, ValidationException):
    """HitBoxバリデーション例外"""

    error_code = "COMBAT.HIT_BOX_VALIDATION"


class HitEffectValidationException(CombatDomainException, ValidationException):
    """HitEffectバリデーション例外"""

    error_code = "COMBAT.HIT_EFFECT_VALIDATION"
