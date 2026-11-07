from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.time_and_weather.changes_every import ChangesEvery, NoChange
from ai_rpg_world.game_world.domain.declaration.time_and_weather.weather_state import WeatherState
from ai_rpg_world.game_world.domain.declaration.time_and_weather.weather_type import WeatherType
from ai_rpg_world.game_world.domain.value_object import DisplayName, Probability


@final
@dataclass(frozen=True)
class WeatherDeclaration:
    initial: WeatherType
    changes: NoChange | ChangesEvery
    announce_changes: bool
    obscuring: frozenset[WeatherType]

    def next_after(self, current: WeatherState, roll: Probability) -> WeatherState:
        return WeatherState(self.changes.next_after(current.type, roll))

    def obscures_sight(self, state: WeatherState) -> bool:
        return state.type in self.obscuring

    def display_name(self, state: WeatherState) -> DisplayName:
        return _DISPLAY_NAMES[state.type]


_DISPLAY_NAMES: dict[WeatherType, DisplayName] = {
    WeatherType.CLEAR: DisplayName("晴れ"),
    WeatherType.CLOUDY: DisplayName("曇り"),
    WeatherType.RAIN: DisplayName("雨"),
    WeatherType.HEAVY_RAIN: DisplayName("豪雨"),
    WeatherType.SNOW: DisplayName("雪"),
    WeatherType.BLIZZARD: DisplayName("吹雪"),
    WeatherType.FOG: DisplayName("霧"),
    WeatherType.STORM: DisplayName("嵐"),
}
