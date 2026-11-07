from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.value_object._checks import require_finite_number


@dataclass(frozen=True)
class Multiplier:
    """0 より大きい倍率 (StealthRule.duration_rate の 2 倍など)。"""

    value: float

    def __post_init__(self) -> None:
        value = require_finite_number("Multiplier", self.value)
        if value <= 0.0:
            raise ValueOutOfRangeException(f"Multiplier must be > 0, got {value}")
        object.__setattr__(self, "value", value)
