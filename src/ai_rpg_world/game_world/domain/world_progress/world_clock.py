from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.eventing import AggregateRoot, DomainEvent, new_event_stamp
from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    DayNightDeclaration,
    DayPhaseName,
    NoDayNight,
    TimeOfDay,
)
from ai_rpg_world.game_world.domain.value_object import Ticks, WorldId, WorldTick


@final
@dataclass(frozen=True)
class WorldTickAdvancedEvent(DomainEvent):
    world_id: WorldId
    before: WorldTick
    after: WorldTick


@final
@dataclass(frozen=True)
class TimeOfDayChangedEvent(DomainEvent):
    world_id: WorldId
    before: DayPhaseName
    after: DayPhaseName
    at: WorldTick


WorldClockEvent = WorldTickAdvancedEvent | TimeOfDayChangedEvent


class WorldClock(AggregateRoot[WorldClockEvent]):
    def __init__(self, world_id: WorldId) -> None:
        super().__init__()
        self._world_id = world_id
        self._now = WorldTick(0)

    @property
    def world_id(self) -> WorldId:
        return self._world_id

    def advance(self, day_night: DayNightDeclaration | NoDayNight) -> None:
        before = self._now
        self._now = before + Ticks(1)
        self.add_event(
            WorldTickAdvancedEvent(**new_event_stamp(), world_id=self._world_id, before=before, after=self._now)
        )
        if isinstance(day_night, NoDayNight):
            return
        phase_before = day_night.phase_at(day_night.time_of_day_at(before))
        phase_after = day_night.phase_at(day_night.time_of_day_at(self._now))
        if phase_before != phase_after:
            self.add_event(
                TimeOfDayChangedEvent(
                    **new_event_stamp(),
                    world_id=self._world_id,
                    before=phase_before.name,
                    after=phase_after.name,
                    at=self._now,
                )
            )

    def now(self) -> WorldTick:
        return self._now

    def time_of_day(self, day_night: DayNightDeclaration) -> TimeOfDay:
        return day_night.time_of_day_at(self._now)
