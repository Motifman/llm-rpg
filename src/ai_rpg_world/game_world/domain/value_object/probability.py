from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.value_object._checks import require_finite_number


@dataclass(frozen=True)
class Probability:
    """0 以上 1 以下の確率。"""

    value: float

    def __post_init__(self) -> None:
        value = require_finite_number("Probability", self.value)
        if not 0.0 <= value <= 1.0:
            raise ValueOutOfRangeException(f"Probability must be within [0, 1], got {value}")
        object.__setattr__(self, "value", value)

    def __add__(self, bonus: Probability) -> Probability:
        if not isinstance(bonus, Probability):
            return NotImplemented
        return Probability(min(1.0, self.value + bonus.value))
