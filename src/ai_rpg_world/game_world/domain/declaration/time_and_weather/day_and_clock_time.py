from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.value_object._checks import require_int_at_least


@final
@dataclass(frozen=True)
class DayAndClockTime:
    day: int
    hour: int
    minute: int

    def __post_init__(self) -> None:
        require_int_at_least("DayAndClockTime.day", self.day, 1)
        require_int_at_least("DayAndClockTime.hour", self.hour, 0)
        require_int_at_least("DayAndClockTime.minute", self.minute, 0)
        if self.hour > 23:
            raise ValueOutOfRangeException(f"DayAndClockTime.hour must be <= 23, got {self.hour}")
        if self.minute > 59:
            raise ValueOutOfRangeException(f"DayAndClockTime.minute must be <= 59, got {self.minute}")
