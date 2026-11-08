from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.value_object._checks import require_int_at_least


@final
@dataclass(frozen=True, order=True)
class TimeOfDay:
    tick_of_day: int

    def __post_init__(self) -> None:
        require_int_at_least("TimeOfDay", self.tick_of_day, 0)
