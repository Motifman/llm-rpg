"""予期 (expectation) のドメイン例外群。"""

from ai_rpg_world.domain.common.exception import (
    BusinessRuleException,
    DomainException,
    NotFoundException,
    StateException,
    ValidationException,
)


class ExpectationDomainException(DomainException):
    """予期ドメインの基底例外。"""

    domain = "expectation"


class ExpectationValidationException(
    ExpectationDomainException, ValidationException
):
    """予期・照合・ID の項目が不正なときの例外。"""

    error_code = "EXPECTATION.VALIDATION"


class ExpectationCheckRuleException(
    ExpectationDomainException, BusinessRuleException
):
    """判定のターンや回数が、作ったターン・前回の判定・期限と矛盾するときの例外。"""

    error_code = "EXPECTATION.CHECK_RULE"


class ExpectationAlreadyClosedException(
    ExpectationDomainException, StateException
):
    """清算待ちを抜けた予期に、さらに判定や期限の確認を渡したときの例外。"""

    error_code = "EXPECTATION.ALREADY_CLOSED"


class ExpectationEventNotFoundException(
    ExpectationDomainException, NotFoundException
):
    """未配信に無い出来事に、配信済みの印を付けようとしたときの例外。"""

    error_code = "EXPECTATION.EVENT_NOT_FOUND"


__all__ = [
    "ExpectationAlreadyClosedException",
    "ExpectationCheckRuleException",
    "ExpectationDomainException",
    "ExpectationEventNotFoundException",
    "ExpectationValidationException",
]
