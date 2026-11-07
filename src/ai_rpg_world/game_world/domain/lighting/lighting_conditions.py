from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.exception.lighting_exception import InvalidLightingConditionsException
from ai_rpg_world.game_world.domain.lighting.lighting import Lighting

_ONE_STEP_DARKER = {
    Lighting.BRIGHT: Lighting.DUSKY,
    Lighting.DUSKY: Lighting.DARK,
    Lighting.DARK: Lighting.PITCH_DARK,
    Lighting.PITCH_DARK: Lighting.PITCH_DARK,
}

_LIT_BY_LIGHT_SOURCE = {
    Lighting.BRIGHT: Lighting.BRIGHT,
    Lighting.DUSKY: Lighting.DUSKY,
    Lighting.DARK: Lighting.DUSKY,
    Lighting.PITCH_DARK: Lighting.DUSKY,
}


@final
@dataclass(frozen=True)
class LightingConditions:
    declared: Lighting
    outdoor: bool
    dark_time_of_day: bool
    weather_obscures: bool
    light_source_present: bool

    def __post_init__(self) -> None:
        if not isinstance(self.declared, Lighting):
            raise InvalidLightingConditionsException(f"declared must be Lighting, got {self.declared!r}")
        _require_bool("outdoor", self.outdoor)
        _require_bool("dark_time_of_day", self.dark_time_of_day)
        _require_bool("weather_obscures", self.weather_obscures)
        _require_bool("light_source_present", self.light_source_present)

    def lighting(self) -> Lighting:
        lighting = self.declared
        if self.outdoor and (self.dark_time_of_day or self.weather_obscures):
            lighting = _ONE_STEP_DARKER[lighting]
        if self.light_source_present:
            lighting = _LIT_BY_LIGHT_SOURCE[lighting]
        return lighting


def _require_bool(name: str, value: object) -> None:
    if not isinstance(value, bool):
        raise InvalidLightingConditionsException(f"{name} must be bool, got {value!r}")
