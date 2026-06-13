"""Being ドメインの例外定義。

DDD の原則に従い、ドメイン固有の意味を持つカスタム例外を使用する。
全ての Being ドメイン例外は ``BeingDomainException`` と適切なカテゴリ例外を
多重継承し、エラーコードは ``BEING.xxx`` の形式で統一する。
"""

from __future__ import annotations

from ai_rpg_world.domain.common.exception import (
    DomainException,
    NotFoundException,
    StateException,
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


class BeingAttachmentValidationException(BeingDomainException, ValidationException):
    """BeingAttachment バリデーション例外 (world_id / player_id の型違反)。"""

    error_code = "BEING.ATTACHMENT_VALIDATION"


class BeingAlreadyAttachedException(BeingDomainException, StateException):
    """既に attachment を持つ Being への再 attach を防ぐ状態遷移例外。

    PR #462 §2.1 (R1): attachment は 0..1。同時に複数の world に乗ることは
    本 PR 時点で不許可 (= YAGNI)。乗り換える場合は先に ``detach`` する。
    """

    error_code = "BEING.ALREADY_ATTACHED"


__all__ = [
    "BeingAlreadyAttachedException",
    "BeingAttachmentValidationException",
    "BeingDomainException",
    "BeingIdValidationException",
    "BeingIdentityValidationException",
    "BeingNotFoundException",
]
