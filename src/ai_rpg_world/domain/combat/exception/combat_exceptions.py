"""
Combatドメインの例外定義
"""

from ai_rpg_world.domain.common.exception import (
    BusinessRuleException,
    DomainException,
    StateException,
    ValidationException
)


class CombatDomainException(DomainException):
    """Combatドメインの基底例外"""
    domain = "combat"


class DamageValidationException(CombatDomainException, ValidationException):
    """ダメージバリデーション例外"""
    error_code = "COMBAT.DAMAGE_VALIDATION"


class HitBoxValidationException(CombatDomainException, ValidationException):
    """HitBoxバリデーション例外"""
    error_code = "COMBAT.HIT_BOX_VALIDATION"


class HitEffectValidationException(CombatDomainException, ValidationException):
    """HitEffectバリデーション例外"""
    error_code = "COMBAT.HIT_EFFECT_VALIDATION"


class CombatTargetNotFoundException(CombatDomainException, BusinessRuleException):
    """戦闘対象未検出例外"""
    error_code = "COMBAT.TARGET_NOT_FOUND"


class HitBoxInactiveException(CombatDomainException, StateException):
    """非アクティブなHitBox操作例外"""
    error_code = "COMBAT.HIT_BOX_INACTIVE"
