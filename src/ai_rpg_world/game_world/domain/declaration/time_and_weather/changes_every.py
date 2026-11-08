from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.time_and_weather.weather_transitions import WeatherTransitions
from ai_rpg_world.game_world.domain.declaration.time_and_weather.weather_type import WeatherType
from ai_rpg_world.game_world.domain.exception.game_world_exception import ValueOutOfRangeException
from ai_rpg_world.game_world.domain.value_object import Probability, Ticks


@final
@dataclass(frozen=True)
class NoChange:
    def next_after(self, current: WeatherType, roll: Probability) -> WeatherType:
        return current


@final
@dataclass(frozen=True)
class ChangesEvery:
    ticks: Ticks
    transitions: WeatherTransitions

    def __post_init__(self) -> None:
        if self.ticks.value < 1:
            raise ValueOutOfRangeException(f"ChangesEvery.ticks must be >= 1, got {self.ticks}")

    def next_after(self, current: WeatherType, roll: Probability) -> WeatherType:
        return self.transitions.next_after(current, roll)
