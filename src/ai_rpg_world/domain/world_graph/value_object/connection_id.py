from dataclasses import dataclass
from typing import Union

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import ConnectionIdValidationException


@dataclass(frozen=True)
class ConnectionId:
    """スポット間接続の一意識別子"""

    value: int

    def __post_init__(self) -> None:
        if self.value <= 0:
            raise ConnectionIdValidationException(f"Connection ID must be positive: {self.value}")

    @classmethod
    def create(cls, value: Union[int, str]) -> "ConnectionId":
        if isinstance(value, str):
            try:
                int_value = int(value)
            except ValueError:
                raise ConnectionIdValidationException(f"Invalid Connection ID format: {value}")
        else:
            int_value = value
        return cls(int_value)

    def __str__(self) -> str:
        return str(self.value)

    def __int__(self) -> int:
        return self.value
