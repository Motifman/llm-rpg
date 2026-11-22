from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.declaration.time_and_weather.day_and_clock_time import DayAndClockTime
from ai_rpg_world.game_world.domain.declaration.time_and_weather.day_phase_declaration import DayPhaseDeclaration
from ai_rpg_world.game_world.domain.declaration.time_and_weather.day_phase_name import DayPhaseName
from ai_rpg_world.game_world.domain.declaration.time_and_weather.time_of_day import TimeOfDay
from ai_rpg_world.game_world.domain.exception.condition_exception import NotDeclaredInThisWorldException
from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.exception.time_and_weather_exception import (
    DayPhaseNameDuplicatedException,
    DayPhasesNotAscendingException,
    NoDayPhasesDeclaredException,
    TimeOfDayBeyondDayException,
    UndeclaredDayPhaseException,
)
from ai_rpg_world.game_world.domain.value_object import Ticks, WorldTick

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.declaration.world_map import WorldMapWording

_MINUTES_PER_DAY = 24 * 60


@final
@dataclass(frozen=True)
class DayPhaseChange:
    before: DayPhaseName
    after: DayPhaseName


@final
@dataclass(frozen=True)
class NoDayNight:
    def is_declared(self) -> bool:
        return False

    def travel_time_text(self, ticks: int, wording: WorldMapWording) -> str:
        return wording.turns.format(turns=ticks)

    def phase_names(self) -> frozenset[DayPhaseName]:
        return frozenset()

    def time_of_day_at(self, now: WorldTick) -> TimeOfDay:
        raise NotDeclaredInThisWorldException("this world declares no day and night")

    def day_and_clock_time_at(self, now: WorldTick) -> DayAndClockTime:
        raise NotDeclaredInThisWorldException("this world declares no day and night")

    def phase_at(self, time_of_day: TimeOfDay) -> DayPhaseDeclaration:
        raise NotDeclaredInThisWorldException("this world declares no day and night")

    def phase_changes(self, before: WorldTick, after: WorldTick) -> tuple[DayPhaseChange, ...]:
        return ()

    def phase_named(self, name: DayPhaseName) -> DayPhaseDeclaration:
        raise NotDeclaredInThisWorldException("this world declares no day and night")

    def declared_phases(self) -> tuple[DayPhaseDeclaration, ...]:
        return ()


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

    def is_declared(self) -> bool:
        return True

    def phase_names(self) -> frozenset[DayPhaseName]:
        return frozenset(phase.name for phase in self.phases)

    def time_of_day_at(self, now: WorldTick) -> TimeOfDay:
        return TimeOfDay((self.starts_at.tick_of_day + now.value) % self.ticks_per_day.value)

    def travel_time_text(self, ticks: int, wording: WorldMapWording) -> str:
        return wording.minutes.format(minutes=ticks * _MINUTES_PER_DAY // self.ticks_per_day.value)

    def day_and_clock_time_at(self, now: WorldTick) -> DayAndClockTime:
        minutes_since_midnight = self.time_of_day_at(now).tick_of_day * _MINUTES_PER_DAY // self.ticks_per_day.value
        return DayAndClockTime(
            day=(self.starts_at.tick_of_day + now.value) // self.ticks_per_day.value + 1,
            hour=minutes_since_midnight // 60,
            minute=minutes_since_midnight % 60,
        )

    def phase_at(self, time_of_day: TimeOfDay) -> DayPhaseDeclaration:
        begun = [phase for phase in self.phases if phase.begins_at <= time_of_day]
        return begun[-1] if begun else self.phases[-1]

    def phase_changes(self, before: WorldTick, after: WorldTick) -> tuple[DayPhaseChange, ...]:
        phase_before = self.phase_at(self.time_of_day_at(before))
        phase_after = self.phase_at(self.time_of_day_at(after))
        if phase_before == phase_after:
            return ()
        return (DayPhaseChange(before=phase_before.name, after=phase_after.name),)

    def declared_phases(self) -> tuple[DayPhaseDeclaration, ...]:
        return self.phases

    def phase_named(self, name: DayPhaseName) -> DayPhaseDeclaration:
        for phase in self.phases:
            if phase.name == name:
                return phase
        raise UndeclaredDayPhaseException(f"day phase {name.value} is not declared")

    def _require_within_day(self, time_of_day: TimeOfDay) -> None:
        if time_of_day.tick_of_day >= self.ticks_per_day.value:
            raise TimeOfDayBeyondDayException(f"{time_of_day} is beyond a day of {self.ticks_per_day}")
