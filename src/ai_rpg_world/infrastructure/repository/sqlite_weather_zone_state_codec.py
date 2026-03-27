"""Pickle codec helpers for WeatherZone snapshots."""

from __future__ import annotations

import pickle

from ai_rpg_world.domain.world.aggregate.weather_zone import WeatherZone


def weather_zone_to_blob(weather_zone: WeatherZone) -> bytes:
    return pickle.dumps(weather_zone, protocol=pickle.HIGHEST_PROTOCOL)


def blob_to_weather_zone(blob: bytes) -> WeatherZone:
    aggregate = pickle.loads(blob)
    if not isinstance(aggregate, WeatherZone):
        raise TypeError(
            "game_weather_zones.aggregate_blob does not contain a WeatherZone instance"
        )
    return aggregate


__all__ = ["blob_to_weather_zone", "weather_zone_to_blob"]
