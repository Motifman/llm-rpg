from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.time_and_weather.weather_type import WeatherType
from ai_rpg_world.game_world.domain.exception.condition_exception import NotDeclaredInThisWorldException


@final
@dataclass(frozen=True)
class WeatherState:
    type: WeatherType


@final
@dataclass(frozen=True)
class NoWeather:
    def initial_state(self) -> NoWeather:
        return self

    def is_declared(self) -> bool:
        return False

    def current(self) -> WeatherState:
        raise NotDeclaredInThisWorldException("this world declares no weather")
