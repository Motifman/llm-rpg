from dataclasses import dataclass
from typing import Union
from ai_rpg_world.domain.world.exception.map_exception import LocationAreaIdValidationException


@dataclass(frozen=True)
class LocationAreaId:
    """ロケーションエリアの識別子"""
    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise LocationAreaIdValidationException(f"LocationAreaId must be positive: {self.value}")

    @classmethod
    def create(cls, value: Union[int, str]) -> "LocationAreaId":
        """intまたはstrからLocationAreaIdを作成"""
        if isinstance(value, str):
            try:
                int_value = int(value)
            except ValueError:
                raise LocationAreaIdValidationException(value)
        else:
            int_value = value

        return cls(int_value)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value
