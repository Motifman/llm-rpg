"""Being ドメインの例外定義。

DDD の原則に従い、ドメイン固有の意味を持つカスタム例外を使用する。
全ての Being ドメイン例外は ``BeingDomainException`` と適切なカテゴリ例外を
多重継承し、エラーコードは ``BEING.xxx`` の形式で統一する。
"""

from __future__ import annotations

from ai_rpg_world.domain.common.exception import (
    DomainException,
    NotFoundException,
    ValidationException,
)


class BeingDomainException(DomainException):
    """Being ドメインの基底例外。

    全ての Being ドメイン例外はこのクラスを継承する。
    """

    domain = "being"


# ===== 具体的な例外クラス =====


class BeingIdValidationException(BeingDomainException, ValidationException):
    """BeingId バリデーション例外。"""

    error_code = "BEING.ID_VALIDATION"


class BeingIdentityValidationException(BeingDomainException, ValidationException):
    """BeingIdentity バリデーション例外 (name / first_person の不正)。"""

    error_code = "BEING.IDENTITY_VALIDATION"


class BeingNotFoundException(BeingDomainException, NotFoundException):
    """指定された BeingId の Being が見つからない場合の例外。"""

    error_code = "BEING.NOT_FOUND"


__all__ = [
    "BeingDomainException",
    "BeingIdValidationException",
    "BeingIdentityValidationException",
    "BeingNotFoundException",
]
