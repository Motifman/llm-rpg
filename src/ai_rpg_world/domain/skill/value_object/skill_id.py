from dataclasses import dataclass
from typing import Union

from ai_rpg_world.domain.skill.exception.skill_exceptions import SkillIdValidationException


@dataclass(frozen=True)
class SkillId:
    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise SkillIdValidationException(f"Skill ID must be positive: {self.value}")

    @classmethod
    def create(cls, value: Union[int, str]) -> "SkillId":
        if isinstance(value, str):
            try:
                parsed = int(value)
            except ValueError as exc:
                raise SkillIdValidationException(f"Invalid skill id: {value}") from exc
            return cls(parsed)
        return cls(value)

    def __int__(self) -> int:
        return self.value

    def __str__(self) -> str:
        return str(self.value)

