"""Intent ドメインの例外定義。

既存パターン (BC 単位の基底 + ValidationException / BusinessRuleException /
NotFoundException との多重継承 + ``error_code`` 属性) に従う。
"""

from ai_rpg_world.domain.common.exception import (
    BusinessRuleException,
    DomainException,
    NotFoundException,
    ValidationException,
)


class IntentDomainException(DomainException):
    """Intent BC の基底例外。"""

    domain = "intent"


class IntentValidationException(IntentDomainException, ValidationException):
    """Intent 値オブジェクト全般のバリデーション例外。"""

    error_code = "INTENT.VALIDATION"


class IntentIdValidationException(IntentDomainException, ValidationException):
    """``IntentId`` のバリデーション例外。"""

    error_code = "INTENT.INTENT_ID_VALIDATION"


class IntentPriorityValidationException(IntentDomainException, ValidationException):
    """``IntentPriority`` のバリデーション例外。"""

    error_code = "INTENT.PRIORITY_VALIDATION"


class DuplicateIntentForPlayerException(IntentDomainException, BusinessRuleException):
    """同一プレイヤーが同一 tick に複数の intent を投稿しようとした。

    並列性の最小単位は「1 プレイヤー / 1 tick」と定義する。LLM が tool を
    複数回呼ぶケースは intent queue 投入時点で BC が拒否する。
    """

    error_code = "INTENT.DUPLICATE_FOR_PLAYER_IN_TICK"


class UnknownIntentException(IntentDomainException, NotFoundException):
    """指定された ``IntentId`` を queue 内に発見できなかった。"""

    error_code = "INTENT.UNKNOWN_ID"
