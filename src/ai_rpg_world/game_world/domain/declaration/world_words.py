from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import final

from ai_rpg_world.game_world.domain.declaration.spot.temperature import Temperature
from ai_rpg_world.game_world.domain.declaration.time_and_weather.weather_type import WeatherType
from ai_rpg_world.game_world.domain.exception.surroundings_texts_exception import MissingWorldWordException
from ai_rpg_world.game_world.domain.lighting import Lighting


@final
@dataclass(frozen=True)
class WorldWords:
    lighting: Mapping[Lighting, str]
    temperature: Mapping[Temperature, str]
    weather: Mapping[WeatherType, str]

    def __post_init__(self) -> None:
        for name, kind in (("lighting", Lighting), ("temperature", Temperature), ("weather", WeatherType)):
            object.__setattr__(self, name, _every_member(name, kind, getattr(self, name)))


def _every_member(name: str, kind: type[Enum], words: Mapping[Enum, str]) -> Mapping[Enum, str]:
    missing = sorted(member.name for member in kind if not str(words.get(member, "")).strip())
    if missing:
        raise MissingWorldWordException(f"WorldWords.{name} lacks words for {missing}")
    return MappingProxyType(dict(words))
