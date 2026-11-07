from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.game_world.domain.value_object._checks import require_int_at_least


@dataclass(frozen=True, order=True)
class HungerAmount:
    value: int

    def __post_init__(self) -> None:
        require_int_at_least("HungerAmount", self.value, 0)

    def __add__(self, other: HungerAmount) -> HungerAmount:
        if not isinstance(other, HungerAmount):
            return NotImplemented
        return HungerAmount(self.value + other.value)
