"""
Skillドメインの例外定義
"""

from ai_rpg_world.domain.common.exception import (
    BusinessRuleException,
    DomainException,
    StateException,
    ValidationException,
)


class SkillDomainException(DomainException):
    """Skillドメインの基底例外"""

    domain = "skill"


class SkillIdValidationException(SkillDomainException, ValidationException):
    error_code = "SKILL.ID_VALIDATION"


class SkillLoadoutIdValidationException(SkillDomainException, ValidationException):
    error_code = "SKILL.LOADOUT_ID_VALIDATION"


class SkillDeckProgressIdValidationException(SkillDomainException, ValidationException):
    error_code = "SKILL.DECK_PROGRESS_ID_VALIDATION"


class SkillSpecValidationException(SkillDomainException, ValidationException):
    error_code = "SKILL.SPEC_VALIDATION"


class SkillHitPatternValidationException(SkillDomainException, ValidationException):
    error_code = "SKILL.HIT_PATTERN_VALIDATION"


class SkillDeckValidationException(SkillDomainException, ValidationException):
    error_code = "SKILL.DECK_VALIDATION"


class SkillDeckCapacityExceededException(SkillDomainException, BusinessRuleException):
    error_code = "SKILL.DECK_CAPACITY_EXCEEDED"


class SkillNotFoundInSlotException(SkillDomainException, StateException):
    error_code = "SKILL.NOT_FOUND_IN_SLOT"


class SkillCooldownActiveException(SkillDomainException, BusinessRuleException):
    error_code = "SKILL.COOLDOWN_ACTIVE"


class SkillCastLockActiveException(SkillDomainException, BusinessRuleException):
    error_code = "SKILL.CAST_LOCK_ACTIVE"


class SkillAwakenStateException(SkillDomainException, StateException):
    error_code = "SKILL.AWAKEN_STATE"


class SkillPrerequisiteNotMetException(SkillDomainException, BusinessRuleException):
    error_code = "SKILL.PREREQUISITE_NOT_MET"


class SkillOwnerMismatchException(SkillDomainException, BusinessRuleException):
    error_code = "SKILL.OWNER_MISMATCH"


class SkillProposalValidationException(SkillDomainException, ValidationException):
    error_code = "SKILL.PROPOSAL_VALIDATION"


class SkillProposalNotFoundException(SkillDomainException, StateException):
    error_code = "SKILL.PROPOSAL_NOT_FOUND"


class SkillAlreadyEquippedException(SkillDomainException, BusinessRuleException):
    """スキルが既に装備されている場合の例外"""
    error_code = "SKILL.ALREADY_EQUIPPED"

