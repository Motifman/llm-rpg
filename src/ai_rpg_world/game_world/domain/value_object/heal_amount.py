from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.game_world.domain.value_object._checks import require_int_at_least


@dataclass(frozen=True)
class HealAmount:
    value: int

    def __post_init__(self) -> None:
        require_int_at_least("HealAmount", self.value, 1)
