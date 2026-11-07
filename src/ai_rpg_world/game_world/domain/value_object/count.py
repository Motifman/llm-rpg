from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.game_world.domain.exception.game_world_exception import CountBelowZeroException
from ai_rpg_world.game_world.domain.value_object._checks import require_int_at_least


@dataclass(frozen=True, order=True)
class Count:
    """物や回数の個数。"""

    value: int

    def __post_init__(self) -> None:
        require_int_at_least("Count", self.value, 0)

    def __add__(self, other: Count) -> Count:
        if not isinstance(other, Count):
            return NotImplemented
        return Count(self.value + other.value)

    def __sub__(self, other: Count) -> Count:
        if not isinstance(other, Count):
            return NotImplemented
        if other > self:
            raise CountBelowZeroException(f"cannot take {other.value} from {self.value}")
        return Count(self.value - other.value)
