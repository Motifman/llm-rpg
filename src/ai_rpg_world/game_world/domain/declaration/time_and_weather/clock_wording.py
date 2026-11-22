from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.time_and_weather.day_and_clock_time import DayAndClockTime
from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException


@final
@dataclass(frozen=True)
class ClockWording:
    day: str
    late_night: str
    late_night_before_hour: int

    def __post_init__(self) -> None:
        # 書けない書き方を、最初に時刻を書くときではなく、読み込みのときに断る
        try:
            written = self.day.format(day=1)
        except (KeyError, IndexError, ValueError) as error:
            raise ValueOutOfRangeException(f"ClockWording.day must name only {{day}}, got {self.day!r}") from error
        if written == self.day:
            raise ValueOutOfRangeException(f"ClockWording.day must name {{day}}, got {self.day!r}")
        if not 0 <= self.late_night_before_hour <= 24:
            raise ValueOutOfRangeException(
                f"ClockWording.late_night_before_hour must be within 0..24, got {self.late_night_before_hour}"
            )

    def display(self, time: DayAndClockTime) -> str:
        late_night = self.late_night if time.hour < self.late_night_before_hour else ""
        return f"{self.day.format(day=time.day)} {late_night}{time.hour}:{time.minute:02d}"
