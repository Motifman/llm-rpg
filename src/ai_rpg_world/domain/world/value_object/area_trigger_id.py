from dataclasses import dataclass
from typing import Union
from ai_rpg_world.domain.world.exception.map_exception import AreaTriggerIdValidationException


@dataclass(frozen=True)
class AreaTriggerId:
    """エリアトリガーの識別子"""
    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise AreaTriggerIdValidationException(f"AreaTriggerId must be positive: {self.value}")

    @classmethod
    def create(cls, value: Union[int, str]) -> "AreaTriggerId":
        """intまたはstrからAreaTriggerIdを作成"""
        if isinstance(value, str):
            try:
                int_value = int(value)
            except ValueError:
                raise AreaTriggerIdValidationException(value)
        else:
            int_value = value

        return cls(int_value)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value
