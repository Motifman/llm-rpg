from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.being.contract import ObservedTime
from ai_rpg_world.game_world.application.command_scope import CommandScope
from ai_rpg_world.game_world.application.observation_exit import observed_time_of
from ai_rpg_world.game_world.domain.declaration.time_and_weather import ClockWording, DayNightDeclaration


@final
@dataclass(frozen=True)
class TellCurrentTimeCommand:
    pass


@final
class TellCurrentTime:
    def __init__(self, scope: CommandScope, day_night: DayNightDeclaration, clock: ClockWording) -> None:
        self._scope = scope
        self._day_night = day_night
        self._clock = clock

    def __call__(self, command: TellCurrentTimeCommand) -> ObservedTime:
        now = self._scope.run(lambda session: session.clock().now())
        return observed_time_of(self._day_night.day_and_clock_time_at(now), self._clock)
