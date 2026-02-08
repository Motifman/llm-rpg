from dataclasses import dataclass
from typing import Union
from ai_rpg_world.domain.world.exception.map_exception import SpotIdValidationException


@dataclass(frozen=True)
class SpotId:
    """スポットの一意識別子"""
    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise SpotIdValidationException(f"Spot ID must be positive: {self.value}")

    @classmethod
    def create(cls, value: Union[int, str]) -> "SpotId":
        """intまたはstrからSpotIdを作成"""
        if isinstance(value, str):
            try:
                int_value = int(value)
            except ValueError:
                raise SpotIdValidationException(f"Invalid Spot ID format (must be an integer): {value}")
        else:
            int_value = value

        return cls(int_value)

    def __str__(self) -> str:
        return str(self.value)
