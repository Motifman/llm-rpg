"""Helpers for normalized WeatherZone persistence."""

from __future__ import annotations

from ai_rpg_world.domain.world.aggregate.weather_zone import WeatherZone
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.value_object.weather_zone_id import WeatherZoneId
from ai_rpg_world.domain.world.value_object.weather_zone_name import WeatherZoneName


def build_weather_zone(
    *,
    zone_id: int,
    name: str,
    weather_type: str,
    intensity: float,
    spot_ids: list[int],
) -> WeatherZone:
    return WeatherZone(
        zone_id=WeatherZoneId(zone_id),
        name=WeatherZoneName(name),
        spot_ids={SpotId(spot_id) for spot_id in spot_ids},
        current_state=WeatherState(WeatherTypeEnum(weather_type), intensity),
    )


__all__ = ["build_weather_zone"]
