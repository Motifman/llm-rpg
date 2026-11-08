from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.condition.aggregate_readings import WorldStageReading
from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.leaf_condition import LeafCondition
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.declaration.progress import WorldStageDeclaration
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.declaration.time_and_weather import DayPhaseName, NoDayNight, NoWeather, WeatherType
from ai_rpg_world.game_world.domain.exception.condition_exception import (
    NotDeclaredInThisWorldException,
    TickModuloOutOfRangeException,
)
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.value_object import Ticks, WorldTick

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts


@final
@dataclass(frozen=True)
class TickAtLeastCondition(LeafCondition):
    tick: WorldTick
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return facts.now() >= self.tick

    def _requirements_besides_text(self) -> Requirements:
        return Requirements.nothing()


@final
@dataclass(frozen=True)
class TickModuloCondition(LeafCondition):
    divisor: Ticks
    remainder: Ticks
    failure_text: TextWithUnassignedPeople | NoText

    def __post_init__(self) -> None:
        if self.divisor < Ticks(1) or self.remainder >= self.divisor:
            raise TickModuloOutOfRangeException(
                f"remainder must be below a divisor of at least 1, got {self.remainder.value} of {self.divisor.value}"
            )

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return facts.now().value % self.divisor.value == self.remainder.value

    def _requirements_besides_text(self) -> Requirements:
        return Requirements.nothing()


def declared_world_stage(facts: WorldFacts) -> WorldStageReading:
    stage = facts.world_stage()
    if isinstance(stage, NoWorldStages):
        raise NotDeclaredInThisWorldException("this world declares no world stages")
    return stage


@final
@dataclass(frozen=True)
class WorldStageIsCondition(LeafCondition):
    stage: WorldStageDeclaration
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return declared_world_stage(facts).current() == self.stage.stage_id

    def _requirements_besides_text(self) -> Requirements:
        return replace(Requirements.nothing(), reads_world_stage=True)


@final
@dataclass(frozen=True)
class TicksInWorldStageAtLeastCondition(LeafCondition):
    ticks: Ticks
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return facts.now().ticks_since(declared_world_stage(facts).entered_at()) >= self.ticks

    def _requirements_besides_text(self) -> Requirements:
        return replace(Requirements.nothing(), reads_world_stage=True)


@final
@dataclass(frozen=True)
class TimeOfDayIsCondition(LeafCondition):
    phase: DayPhaseName
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        day_night = facts.day_night()
        if isinstance(day_night, NoDayNight):
            raise NotDeclaredInThisWorldException("this world declares no day and night")
        return day_night.phase_at(facts.clock().time_of_day(day_night)).name == self.phase

    def _requirements_besides_text(self) -> Requirements:
        return replace(Requirements.nothing(), reads_day_phases=frozenset({self.phase}))


@final
@dataclass(frozen=True)
class WeatherIsCondition(LeafCondition):
    weather: WeatherType
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        weather = facts.weather()
        if isinstance(weather, NoWeather):
            raise NotDeclaredInThisWorldException("this world declares no weather")
        return weather.current().type is self.weather

    def _requirements_besides_text(self) -> Requirements:
        return replace(Requirements.nothing(), reads_weather=True)
