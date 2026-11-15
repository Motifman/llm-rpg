from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.declaration.time_and_weather.weather_type import WeatherType
from ai_rpg_world.game_world.domain.exception.condition_exception import NotDeclaredInThisWorldException

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.condition.random_source import RandomSource
    from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates
    from ai_rpg_world.game_world.domain.value_object import WorldTick


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

    def obscures_sight(self, state: WeatherState) -> bool:
        return False

    def current(self) -> WeatherState:
        raise NotDeclaredInThisWorldException("this world declares no weather")

    def pass_time_in(self, world: WorldAggregates, now: WorldTick, random: RandomSource) -> None:
        pass
