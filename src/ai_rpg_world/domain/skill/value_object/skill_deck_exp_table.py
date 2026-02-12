from dataclasses import dataclass

from ai_rpg_world.domain.skill.exception.skill_exceptions import SkillProposalValidationException


@dataclass(frozen=True)
class SkillDeckExpTable:
    base_exp: int = 50
    exponent: float = 1.5
    level_offset: int = 1

    def __post_init__(self):
        if self.base_exp <= 0:
            raise SkillProposalValidationException(f"base_exp must be positive: {self.base_exp}")
        if self.exponent <= 0:
            raise SkillProposalValidationException(f"exponent must be positive: {self.exponent}")
        if self.level_offset < 0:
            raise SkillProposalValidationException(
                f"level_offset cannot be negative: {self.level_offset}"
            )

    def get_required_exp_for_level(self, level: int) -> int:
        if level <= 1:
            return 0
        return int(self.base_exp * ((level - 1 + self.level_offset) ** self.exponent))

