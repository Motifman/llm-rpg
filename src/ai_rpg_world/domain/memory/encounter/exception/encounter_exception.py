"""Encounter Memory ドメイン例外群。

Encounter Memory は「自分が初めて見たもの / すでに会った相手」を familiarity
信号として保持する記憶層。docs/memory_system/perception_memory_join_design.md
を参照。

不変条件違反は基底の ``EncounterDomainException`` 配下の ValidationException で
表現する。
"""

from ai_rpg_world.domain.common.exception import (
    BusinessRuleException,
    DomainException,
    ValidationException,
)


class EncounterDomainException(DomainException):
    """Encounter Memory ドメインの基底例外。"""

    domain = "memory.encounter"


class EncounterKeyValidationException(EncounterDomainException, ValidationException):
    """``EncounterKey`` のバリデーション例外 (kind / identifier の不正)。"""

    error_code = "ENCOUNTER.KEY_VALIDATION"


class EncounterRecordValidationException(
    EncounterDomainException, ValidationException
):
    """``EncounterRecord`` のバリデーション例外 (tick / count の不正)。"""

    error_code = "ENCOUNTER.RECORD_VALIDATION"


class EncounterRecordRuleException(EncounterDomainException, BusinessRuleException):
    """``EncounterRecord`` の業務ルール違反 (時系列の逆行など)。"""

    error_code = "ENCOUNTER.RECORD_RULE"


__all__ = [
    "EncounterDomainException",
    "EncounterKeyValidationException",
    "EncounterRecordValidationException",
    "EncounterRecordRuleException",
]
