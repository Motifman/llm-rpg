from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.game_world.domain.value_object._checks import require_int_at_least


@dataclass(frozen=True, order=True)
class FatigueAmount:
    """疲れの量。"""

    value: int

    def __post_init__(self) -> None:
        require_int_at_least("FatigueAmount", self.value, 0)

    def __add__(self, other: FatigueAmount) -> FatigueAmount:
        if not isinstance(other, FatigueAmount):
            return NotImplemented
        return FatigueAmount(self.value + other.value)
