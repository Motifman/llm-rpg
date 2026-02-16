"""
行動ロジックに関連する例外定義
"""

from ai_rpg_world.domain.world.exception.map_exception import MapDomainException
from ai_rpg_world.domain.common.exception import BusinessRuleException, ValidationException, StateException


class BehaviorDomainException(MapDomainException):
    """行動ロジックドメインの基底例外"""
    domain = "world.behavior"


class InvalidBehaviorStateException(BehaviorDomainException, StateException):
    """不正な行動状態への遷移または操作の例外"""
    error_code = "BEHAVIOR.INVALID_STATE"


class NoTargetSpecifiedException(BehaviorDomainException, BusinessRuleException):
    """ターゲットが指定されていない場合の例外"""
    error_code = "BEHAVIOR.NO_TARGET_SPECIFIED"


class VisionRangeValidationException(BehaviorDomainException, ValidationException):
    """視界範囲のバリデーション例外"""
    error_code = "BEHAVIOR.VISION_RANGE_VALIDATION"


class FOVAngleValidationException(BehaviorDomainException, ValidationException):
    """視野角のバリデーション例外"""
    error_code = "BEHAVIOR.FOV_ANGLE_VALIDATION"


class InvalidPatrolPointException(BehaviorDomainException, ValidationException):
    """巡回ポイントのバリデーション例外"""
    error_code = "BEHAVIOR.INVALID_PATROL_POINT"


class SearchDurationValidationException(BehaviorDomainException, ValidationException):
    """探索時間のバリデーション例外"""
    error_code = "BEHAVIOR.SEARCH_DURATION_VALIDATION"


class HPPercentageValidationException(BehaviorDomainException, ValidationException):
    """HP割合のバリデーション例外"""
    error_code = "BEHAVIOR.HP_PERCENTAGE_VALIDATION"


class FleeThresholdValidationException(BehaviorDomainException, ValidationException):
    """逃走閾値のバリデーション例外"""
    error_code = "BEHAVIOR.FLEE_THRESHOLD_VALIDATION"


class MaxFailuresValidationException(BehaviorDomainException, ValidationException):
    """最大失敗回数のバリデーション例外"""
    error_code = "BEHAVIOR.MAX_FAILURES_VALIDATION"


class ComponentRequiredForDispositionException(BehaviorDomainException, ValidationException):
    """関係判定に必要な component が None の場合の例外。WorldObject は component を持つ前提。"""
    error_code = "BEHAVIOR.COMPONENT_REQUIRED_FOR_DISPOSITION"


class GrowthContextValidationException(BehaviorDomainException, ValidationException):
    """GrowthContext のバリデーション例外（effective_flee_threshold や allow_chase の不正値）"""
    error_code = "BEHAVIOR.GROWTH_CONTEXT_VALIDATION"


class HungerValidationException(BehaviorDomainException, ValidationException):
    """飢餓値のバリデーション例外（0.0〜1.0 の範囲外など）"""
    error_code = "BEHAVIOR.HUNGER_VALIDATION"
