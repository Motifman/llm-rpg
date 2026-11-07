from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.value_object._checks import require_finite_number


@dataclass(frozen=True)
class Rate:
    """0 以上 1 以下の割合。1 を超える倍率は Multiplier で表す。"""

    value: float

    def __post_init__(self) -> None:
        value = require_finite_number("Rate", self.value)
        if not 0.0 <= value <= 1.0:
            raise ValueOutOfRangeException(f"Rate must be within [0, 1], got {value}")
        object.__setattr__(self, "value", value)
