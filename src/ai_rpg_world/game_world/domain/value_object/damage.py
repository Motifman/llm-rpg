from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.game_world.domain.value_object._checks import require_int_at_least


@dataclass(frozen=True)
class Damage:
    value: int

    def __post_init__(self) -> None:
        require_int_at_least("Damage", self.value, 1)
