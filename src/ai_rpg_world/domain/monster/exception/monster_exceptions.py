"""
Monsterドメインの例外定義
"""

from ai_rpg_world.domain.common.exception import (
    BusinessRuleException,
    DomainException,
    StateException,
    ValidationException
)


class MonsterDomainException(DomainException):
    """Monsterドメインの基底例外"""
    domain = "monster"


class MonsterIdValidationException(MonsterDomainException, ValidationException):
    """モンスターIDバリデーション例外"""
    error_code = "MONSTER.ID_VALIDATION"


class MonsterTemplateIdValidationException(MonsterDomainException, ValidationException):
    """モンスターテンプレートIDバリデーション例外"""
    error_code = "MONSTER.TEMPLATE_ID_VALIDATION"


class MonsterStatsValidationException(MonsterDomainException, ValidationException):
    """モンスターステータスバリデーション例外"""
    error_code = "MONSTER.STATS_VALIDATION"


class MonsterRewardValidationException(MonsterDomainException, ValidationException):
    """モンスター報酬バリデーション例外"""
    error_code = "MONSTER.REWARD_VALIDATION"


class MonsterRespawnValidationException(MonsterDomainException, ValidationException):
    """モンスターリスポーンバリデーション例外"""
    error_code = "MONSTER.RESPAWN_VALIDATION"


class MonsterAlreadyDeadException(MonsterDomainException, StateException):
    """モンスター既に死亡例外"""
    error_code = "MONSTER.ALREADY_DEAD"


class MonsterNotSpawnedException(MonsterDomainException, StateException):
    """モンスター未出現例外"""
    error_code = "MONSTER.NOT_SPAWNED"


class MonsterAlreadySpawnedException(MonsterDomainException, StateException):
    """モンスター既に出現済み例外"""
    error_code = "MONSTER.ALREADY_SPAWNED"


class MonsterNotDeadException(MonsterDomainException, StateException):
    """モンスター生存中例外（リスポーン不可）"""
    error_code = "MONSTER.NOT_DEAD"


class MonsterRespawnIntervalNotMetException(MonsterDomainException, BusinessRuleException):
    """モンスターリスポーン間隔未充足例外"""
    error_code = "MONSTER.RESPAWN_INTERVAL_NOT_MET"


class MonsterInsufficientMpException(MonsterDomainException, BusinessRuleException):
    """MP不足例外"""
    error_code = "MONSTER.INSUFFICIENT_MP"


class MonsterTemplateValidationException(MonsterDomainException, ValidationException):
    """モンスターテンプレートバリデーション例外"""
    error_code = "MONSTER.TEMPLATE_VALIDATION"
