from dataclasses import dataclass
from typing import Union

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import SpotObjectIdValidationException


@dataclass(frozen=True)
class SpotObjectId:
    value: int

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise SpotObjectIdValidationException(f"Spot object ID must be positive: {self.value}")

    @classmethod
    def create(cls, value: Union[int, str]) -> "SpotObjectId":
        if isinstance(value, str):
            try:
                int_value = int(value)
            except ValueError:
                raise SpotObjectIdValidationException(f"Invalid spot object ID format: {value}")
        else:
            int_value = value
        return cls(int_value)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value
