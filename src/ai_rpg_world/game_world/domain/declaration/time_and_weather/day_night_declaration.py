from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.time_and_weather.day_phase_declaration import DayPhaseDeclaration
from ai_rpg_world.game_world.domain.declaration.time_and_weather.time_of_day import TimeOfDay
from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.exception.time_and_weather_exception import (
    DayPhaseNameDuplicatedException,
    DayPhasesNotAscendingException,
    NoDayPhasesDeclaredException,
    TimeOfDayBeyondDayException,
)
from ai_rpg_world.game_world.domain.value_object import Ticks, WorldTick


@final
@dataclass(frozen=True)
class NoDayNight:
    pass


@final
@dataclass(frozen=True)
class DayNightDeclaration:
    ticks_per_day: Ticks
    starts_at: TimeOfDay
    phases: tuple[DayPhaseDeclaration, ...]

    def __post_init__(self) -> None:
        if self.ticks_per_day.value < 1:
            raise ValueOutOfRangeException(f"ticks_per_day must be >= 1, got {self.ticks_per_day}")
        if not self.phases:
            raise NoDayPhasesDeclaredException("DayNightDeclaration needs at least one phase")
        self._require_within_day(self.starts_at)
        for phase in self.phases:
            self._require_within_day(phase.begins_at)
        for earlier, later in zip(self.phases, self.phases[1:]):
            if later.begins_at <= earlier.begins_at:
                raise DayPhasesNotAscendingException(
                    f"{later.name} begins at {later.begins_at}, not after {earlier.name} at {earlier.begins_at}"
                )
        names = [phase.name for phase in self.phases]
        if len(set(names)) != len(names):
            raise DayPhaseNameDuplicatedException(f"day phase names must be unique, got {names}")

    def time_of_day_at(self, now: WorldTick) -> TimeOfDay:
        return TimeOfDay((self.starts_at.tick_of_day + now.value) % self.ticks_per_day.value)

    def phase_at(self, time_of_day: TimeOfDay) -> DayPhaseDeclaration:
        begun = [phase for phase in self.phases if phase.begins_at <= time_of_day]
        # 最初の段階より前の時刻は、前の日の最後の段階が続いている。
        return begun[-1] if begun else self.phases[-1]

    def _require_within_day(self, time_of_day: TimeOfDay) -> None:
        if time_of_day.tick_of_day >= self.ticks_per_day.value:
            raise TimeOfDayBeyondDayException(f"{time_of_day} is beyond a day of {self.ticks_per_day}")
