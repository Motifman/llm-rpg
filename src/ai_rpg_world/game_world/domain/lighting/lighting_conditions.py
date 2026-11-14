from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.exception.lighting_exception import InvalidLightingConditionsException
from ai_rpg_world.game_world.domain.lighting.lighting import Lighting

if TYPE_CHECKING:
    # 実行時に import すると循環する。
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration

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

    @classmethod
    def at(cls, spot: SpotDeclaration, facts: WorldFacts) -> LightingConditions:
        atmosphere = facts.atmospheres().atmosphere_of(spot)
        return cls(
            declared=atmosphere.lighting,
            outdoor=atmosphere.outdoor,
            dark_time_of_day=_is_dark_time_of_day(facts),
            weather_obscures=_weather_obscures_sight(facts),
            light_source_present=_light_source_held_at(spot, facts),
        )

    def lighting(self) -> Lighting:
        lighting = self.declared
        if self.outdoor and (self.dark_time_of_day or self.weather_obscures):
            lighting = _ONE_STEP_DARKER[lighting]
        if self.light_source_present:
            lighting = _LIT_BY_LIGHT_SOURCE[lighting]
        return lighting


def _is_dark_time_of_day(facts: WorldFacts) -> bool:
    day_night = facts.day_night()
    return day_night.is_declared() and day_night.phase_at(facts.clock().time_of_day(day_night)).dark


def _weather_obscures_sight(facts: WorldFacts) -> bool:
    weather = facts.weather_declaration()
    return weather.is_declared() and weather.obscures_sight(facts.weather().current())


def _light_source_held_at(spot: SpotDeclaration, facts: WorldFacts) -> bool:
    return any(
        facts.item(item).gives_light()
        for occupant in facts.whereabouts().occupants_at(spot)
        if occupant.can_hold_items()
        for item in facts.inventory(occupant.person).held_items()
    )


def _require_bool(name: str, value: object) -> None:
    if not isinstance(value, bool):
        raise InvalidLightingConditionsException(f"{name} must be bool, got {value!r}")
