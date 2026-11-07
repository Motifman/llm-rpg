from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.game_world.domain.exception.game_world_exception import InsufficientGoldException
from ai_rpg_world.game_world.domain.value_object._checks import require_int_at_least


@dataclass(frozen=True, order=True)
class Gold:
    value: int

    def __post_init__(self) -> None:
        require_int_at_least("Gold", self.value, 0)

    def __add__(self, other: Gold) -> Gold:
        if not isinstance(other, Gold):
            return NotImplemented
        return Gold(self.value + other.value)

    def __sub__(self, other: Gold) -> Gold:
        if not isinstance(other, Gold):
            return NotImplemented
        if other > self:
            raise InsufficientGoldException(f"cannot pay {other.value} from {self.value}")
        return Gold(self.value - other.value)
