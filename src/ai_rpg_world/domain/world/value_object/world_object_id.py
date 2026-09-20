from dataclasses import dataclass
from typing import Union

from ai_rpg_world.domain.world.exception.map_exception import WorldObjectIdValidationException


@dataclass(frozen=True)
class WorldObjectId:
    """ワールドオブジェクトの一意識別子"""
    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise WorldObjectIdValidationException(f"WorldObject ID must be positive: {self.value}")

    @classmethod
    def create(cls, value: int | str) -> "WorldObjectId":
        """intまたはstrからWorldObjectIdを作成"""
        if isinstance(value, str):
            try:
                int_value = int(value)
            except ValueError:
                raise WorldObjectIdValidationException(value)
        else:
            int_value = value

        return cls(int_value)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value
