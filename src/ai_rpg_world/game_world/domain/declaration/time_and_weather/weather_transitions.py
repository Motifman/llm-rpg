from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.declaration.time_and_weather.weather_type import WeatherType
from ai_rpg_world.game_world.domain.exception.time_and_weather_exception import (
    NoNextWeatherDeclaredException,
    WeatherTransitionDuplicatedException,
)
from ai_rpg_world.game_world.domain.value_object import Probability
from ai_rpg_world.game_world.domain.value_object._checks import require_int_at_least


@final
@dataclass(frozen=True)
class WeightedWeather:
    weather: WeatherType
    weight: int

    def __post_init__(self) -> None:
        require_int_at_least("WeightedWeather.weight", self.weight, 1)


@final
@dataclass(frozen=True)
class WeatherTransitionRow:
    current: WeatherType
    candidates: tuple[WeightedWeather, ...]

    def __post_init__(self) -> None:
        if not self.candidates:
            raise NoNextWeatherDeclaredException(f"{self.current} has no next weather")
        weathers = [candidate.weather for candidate in self.candidates]
        if len(set(weathers)) != len(weathers):
            raise WeatherTransitionDuplicatedException(f"{self.current} lists a next weather twice: {weathers}")

    def pick(self, roll: Probability) -> WeatherType:
        threshold = roll.value * sum(candidate.weight for candidate in self.candidates)
        cumulative = 0
        for candidate in self.candidates:
            cumulative += candidate.weight
            if threshold < cumulative:
                return candidate.weather
        return self.candidates[-1].weather


@final
@dataclass(frozen=True)
class WeatherTransitions:
    rows: tuple[WeatherTransitionRow, ...]

    def __post_init__(self) -> None:
        currents = [row.current for row in self.rows]
        if len(set(currents)) != len(currents):
            raise WeatherTransitionDuplicatedException(f"a weather has two rows: {currents}")

    @classmethod
    def default(cls) -> WeatherTransitions:
        return cls(
            rows=tuple(
                WeatherTransitionRow(
                    current=current,
                    candidates=tuple(WeightedWeather(weather=w, weight=n) for w, n in candidates),
                )
                for current, candidates in _DEFAULT_WEIGHTS
            )
        )

    def next_after(self, current: WeatherType, roll: Probability) -> WeatherType:
        for row in self.rows:
            if row.current == current:
                return row.pick(roll)
        return current


_DEFAULT_WEIGHTS: tuple[tuple[WeatherType, tuple[tuple[WeatherType, int], ...]], ...] = (
    (WeatherType.CLEAR, ((WeatherType.CLEAR, 70), (WeatherType.CLOUDY, 25), (WeatherType.FOG, 5))),
    (
        WeatherType.CLOUDY,
        (
            (WeatherType.CLEAR, 30),
            (WeatherType.CLOUDY, 40),
            (WeatherType.RAIN, 15),
            (WeatherType.SNOW, 5),
            (WeatherType.FOG, 10),
        ),
    ),
    (
        WeatherType.RAIN,
        ((WeatherType.CLOUDY, 30), (WeatherType.RAIN, 40), (WeatherType.HEAVY_RAIN, 20), (WeatherType.STORM, 10)),
    ),
    (WeatherType.HEAVY_RAIN, ((WeatherType.RAIN, 50), (WeatherType.HEAVY_RAIN, 30), (WeatherType.STORM, 20))),
    (WeatherType.SNOW, ((WeatherType.CLOUDY, 40), (WeatherType.SNOW, 50), (WeatherType.BLIZZARD, 10))),
    (WeatherType.BLIZZARD, ((WeatherType.SNOW, 60), (WeatherType.BLIZZARD, 40))),
    (WeatherType.FOG, ((WeatherType.CLEAR, 40), (WeatherType.CLOUDY, 30), (WeatherType.FOG, 30))),
    (WeatherType.STORM, ((WeatherType.RAIN, 40), (WeatherType.HEAVY_RAIN, 30), (WeatherType.STORM, 30))),
)
