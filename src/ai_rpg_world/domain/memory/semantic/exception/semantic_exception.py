"""Semantic Memory ドメイン例外群。

U2 (証拠台帳統一設計 §2): ``BeliefEvidence`` VO の不変条件違反は、他の
bounded context (``domain/memory/encounter/exception`` 等) と同じパターンで
``SemanticDomainException`` 配下の ``ValidationException`` として表現する。
組み込み ``ValueError`` / ``TypeError`` は domain 層では使わない
(CLAUDE.md 「ドメイン層では組み込み例外ではなくドメイン例外を投げる」)。
"""

from ai_rpg_world.domain.common.exception import (
    BusinessRuleException,
    DomainException,
    ValidationException,
)


class SemanticDomainException(DomainException):
    """Semantic Memory ドメインの基底例外。"""

    domain = "memory.semantic"


class BeliefEvidenceValidationException(SemanticDomainException, ValidationException):
    """``BeliefEvidence`` のバリデーション例外 (フィールドの型 / 空文字 / 未知値)。"""

    error_code = "SEMANTIC.BELIEF_EVIDENCE_VALIDATION"


class BeliefEvidenceRuleException(SemanticDomainException, BusinessRuleException):
    """``BeliefEvidence`` に関する業務ルール違反 (将来の容量上限等で使用予定)。"""

    error_code = "SEMANTIC.BELIEF_EVIDENCE_RULE"


class SemanticMemoryEntryValidationException(
    SemanticDomainException, ValidationException
):
    """``SemanticMemoryEntry`` の belief journal 拡張フィールド (U3a) の

    バリデーション例外 (status の未知値・belief_id / supersedes / 証拠 id 群の
    型・空文字違反)。既存フィールドのバリデーションは ``ValueError`` /
    ``TypeError`` のまま現状維持しているため、本例外は U3a で追加した
    フィールドにのみ用いる。
    """

    error_code = "SEMANTIC.MEMORY_ENTRY_VALIDATION"


__all__ = [
    "SemanticDomainException",
    "BeliefEvidenceValidationException",
    "BeliefEvidenceRuleException",
    "SemanticMemoryEntryValidationException",
]
