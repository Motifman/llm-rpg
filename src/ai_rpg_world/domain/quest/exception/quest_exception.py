"""
Questドメインの例外定義

DDDの原則に従い、ドメイン固有の意味を持つカスタム例外を使用します。
全てのQuestドメイン例外はQuestDomainExceptionと適切なカテゴリ例外を多重継承し、
エラーコードは"QUEST.xxx"の形式で統一します。
"""

from ai_rpg_world.domain.common.exception import (
    BusinessRuleException,
    DomainException,
    StateException,
    ValidationException,
)


class QuestDomainException(DomainException):
    """Questドメインの基底例外

    全てのQuestドメイン例外はこのクラスを継承します。
    """
    domain = "quest"


# ===== 具体的な例外クラス =====

class QuestIdValidationException(QuestDomainException, ValidationException):
    """クエストIDバリデーション例外"""
    error_code = "QUEST.ID_VALIDATION"


class QuestScopeValidationException(QuestDomainException, ValidationException):
    """クエスト範囲バリデーション例外"""
    error_code = "QUEST.SCOPE_VALIDATION"


class InvalidQuestStatusException(QuestDomainException, StateException):
    """無効なクエスト状態例外"""
    error_code = "QUEST.INVALID_STATUS"


class CannotAcceptQuestException(QuestDomainException, BusinessRuleException):
    """クエストを受託できない例外"""
    error_code = "QUEST.CANNOT_ACCEPT"


class CannotCancelQuestException(QuestDomainException, BusinessRuleException):
    """クエストをキャンセルできない例外"""
    error_code = "QUEST.CANNOT_CANCEL"


class QuestObjectiveNotFoundException(QuestDomainException, BusinessRuleException):
    """該当する目標が見つからない例外"""
    error_code = "QUEST.OBJECTIVE_NOT_FOUND"


class QuestObjectivesNotCompleteException(QuestDomainException, StateException):
    """全目標が未達成のため完了できない例外"""
    error_code = "QUEST.OBJECTIVES_NOT_COMPLETE"


class QuestAlreadyCompletedException(QuestDomainException, StateException):
    """クエストが既に完了している例外"""
    error_code = "QUEST.ALREADY_COMPLETED"
