from dataclasses import dataclass
from typing import Union

from ai_rpg_world.domain.skill.exception.skill_exceptions import (
    SkillLoadoutIdValidationException,
)


@dataclass(frozen=True)
class SkillLoadoutId:
    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise SkillLoadoutIdValidationException(
                f"Skill loadout ID must be positive: {self.value}"
            )

    @classmethod
    def create(cls, value: Union[int, str]) -> "SkillLoadoutId":
        if isinstance(value, str):
            try:
                parsed = int(value)
            except ValueError as exc:
                raise SkillLoadoutIdValidationException(
                    f"Invalid skill loadout id: {value}"
                ) from exc
            return cls(parsed)
        return cls(value)

    def __int__(self) -> int:
        return self.value

    def __str__(self) -> str:
        return str(self.value)

