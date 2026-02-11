from dataclasses import dataclass
from typing import Union
from ai_rpg_world.domain.monster.exception.monster_exceptions import MonsterIdValidationException


@dataclass(frozen=True)
class MonsterId:
    """モンスター個体ID値オブジェクト"""
    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise MonsterIdValidationException(f"Monster ID must be positive: {self.value}")

    @classmethod
    def create(cls, value: Union[int, str]) -> "MonsterId":
        if isinstance(value, str):
            try:
                int_value = int(value)
            except ValueError:
                raise MonsterIdValidationException(value)
        else:
            int_value = value

        return cls(int_value)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value
