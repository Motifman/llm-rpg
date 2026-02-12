from dataclasses import dataclass
from typing import Union

from ai_rpg_world.domain.skill.exception.skill_exceptions import (
    SkillDeckProgressIdValidationException,
)


@dataclass(frozen=True)
class SkillDeckProgressId:
    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise SkillDeckProgressIdValidationException(
                f"Skill deck progress ID must be positive: {self.value}"
            )

    @classmethod
    def create(cls, value: Union[int, str]) -> "SkillDeckProgressId":
        if isinstance(value, str):
            try:
                parsed = int(value)
            except ValueError as exc:
                raise SkillDeckProgressIdValidationException(
                    f"Invalid skill deck progress id: {value}"
                ) from exc
            return cls(parsed)
        return cls(value)

    def __int__(self) -> int:
        return self.value

    def __str__(self) -> str:
        return str(self.value)

