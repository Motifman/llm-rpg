from dataclasses import dataclass
from typing import Union
from ai_rpg_world.domain.combat.exception.combat_exceptions import HitBoxValidationException


@dataclass(frozen=True)
class HitBoxId:
    """HitBox一意識別子"""
    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise HitBoxValidationException(f"HitBox ID must be positive: {self.value}")

    @classmethod
    def create(cls, value: Union[int, str]) -> "HitBoxId":
        if isinstance(value, str):
            try:
                int_value = int(value)
            except ValueError:
                raise HitBoxValidationException(value)
        else:
            int_value = value
        return cls(int_value)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value
