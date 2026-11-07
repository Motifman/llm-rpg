from __future__ import annotations

from enum import Enum


class WeatherType(Enum):
    CLEAR = "CLEAR"
    CLOUDY = "CLOUDY"
    RAIN = "RAIN"
    HEAVY_RAIN = "HEAVY_RAIN"
    SNOW = "SNOW"
    BLIZZARD = "BLIZZARD"
    FOG = "FOG"
    STORM = "STORM"
