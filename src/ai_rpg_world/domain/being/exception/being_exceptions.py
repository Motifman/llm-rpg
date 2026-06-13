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


class BeingSnapshotIncompleteException(BeingDomainException, ValidationException):
    """BeingSnapshot の構造が不整合な場合に投げる例外。

    PR #462 §2.1 R1 「all-or-nothing で復元の完全性を保証 (部分復元を構造的に
    禁止)」を強制する例外。snapshot の attachment フィールドが片方だけ埋まって
    いる / 認識できない memory_kind が含まれる等の構造的破綻時に投げる。
    """

    error_code = "BEING.SNAPSHOT_INCOMPLETE"


class BeingMultipleAttachmentException(BeingDomainException, StateException):
    """同一 (world, player) に 2 つ以上の Being が attach 済みという異常状態。

    PR #462 §2.1 R1 / Phase 2 PR2: attachment は 0..1 が不変条件。Being.attach
    側で多重 attach は弾いているが、Repository を直接書く経路や永続化された
    異常データから読み戻した場合に備え、Resolver で検出して本例外を投げる。

    状態遷移の整合性破壊なので StateException 系。
    """

    error_code = "BEING.MULTIPLE_ATTACHMENT"


class BeingSnapshotVersionException(BeingDomainException, ValidationException):
    """BeingSnapshot のバージョンが現バージョン codec で復元不能な場合に投げる例外。

    将来の schema 進化に備えた構造化バージョニング (= 設計判断 5)。古い snapshot
    を新 codec で読む場合の明示的なフォールバック地点として使う。
    """

    error_code = "BEING.SNAPSHOT_VERSION"


__all__ = [
    "BeingAlreadyAttachedException",
    "BeingAttachmentValidationException",
    "BeingDomainException",
    "BeingIdValidationException",
    "BeingIdentityValidationException",
    "BeingMultipleAttachmentException",
    "BeingNotFoundException",
    "BeingSnapshotIncompleteException",
    "BeingSnapshotVersionException",
]
