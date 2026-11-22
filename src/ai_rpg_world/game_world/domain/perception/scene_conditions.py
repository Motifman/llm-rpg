from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.declaration.spot import NoAmbientSound, NoSmell, SpotAtmosphere
from ai_rpg_world.game_world.domain.declaration.time_and_weather import NoDayNight, NoWeather
from ai_rpg_world.game_world.domain.declaration.time_and_weather.day_and_clock_time import DayAndClockTime
from ai_rpg_world.game_world.domain.declaration.time_and_weather.day_phase_declaration import DayPhaseDeclaration
from ai_rpg_world.game_world.domain.declaration.time_and_weather.weather_type import WeatherType
from ai_rpg_world.game_world.domain.lighting import Lighting

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration
    from ai_rpg_world.game_world.domain.declaration.surroundings_texts import SceneTexts
    from ai_rpg_world.game_world.domain.declaration.time_and_weather.clock_wording import ClockWording
    from ai_rpg_world.game_world.domain.declaration.world_words import WorldWords


@final
@dataclass(frozen=True)
class SceneConditions:
    atmosphere: SpotAtmosphere
    lighting: Lighting
    weather: WeatherType | None
    time: DayAndClockTime | None
    phase: DayPhaseDeclaration | None

    @classmethod
    def at(cls, spot: SpotDeclaration, facts: WorldFacts, lighting: Lighting) -> SceneConditions:
        atmosphere = facts.atmospheres().atmosphere_of(spot)
        weather = facts.weather()
        day_night = facts.day_night()
        if isinstance(day_night, NoDayNight):
            time, phase = None, None
        else:
            now = facts.now()
            time = day_night.day_and_clock_time_at(now)
            phase = day_night.phase_at(day_night.time_of_day_at(now))
        return cls(
            atmosphere=atmosphere,
            lighting=lighting,
            weather=None if isinstance(weather, NoWeather) or not atmosphere.outdoor else weather.current().type,
            time=time,
            phase=phase,
        )

    def lines(self, texts: SceneTexts, words: WorldWords, clock: ClockWording) -> list[str]:
        lines = [texts.atmosphere.format(parts=texts.atmosphere_joiner.join(self._atmosphere_parts(texts, words)))]
        if self.weather is not None:
            lines.append(texts.weather.format(weather=words.weather[self.weather]))
        if self.time is not None:
            lines.append(texts.clock.format(time=clock.display(self.time)))
        if self.phase is not None:
            phase_text = texts.dark_day_phase if self.phase.dark else texts.day_phase
            lines.append(phase_text.format(phase=self.phase.display_name.text))
        return lines

    def _atmosphere_parts(self, texts: SceneTexts, words: WorldWords) -> list[str]:
        parts = [texts.lighting.format(lighting=words.lighting[self.lighting])]
        if not isinstance(self.atmosphere.ambient_sound, NoAmbientSound):
            parts.append(texts.sound.format(sound=self.atmosphere.ambient_sound.text))
        parts.append(texts.temperature.format(temperature=words.temperature[self.atmosphere.temperature]))
        if not isinstance(self.atmosphere.smell, NoSmell):
            parts.append(texts.smell.format(smell=self.atmosphere.smell.text))
        return parts
