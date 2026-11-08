from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from functools import reduce
from typing import Any, final

from ai_rpg_world.game_world.domain.condition.condition import Condition
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.declaration.progress import (
    FlagDeclaration,
    GroupDecisionDeclaration,
    WorldStageDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.progress.no_world_stages import NoWorldStages
from ai_rpg_world.game_world.domain.declaration.rule_placement import RulePlacement
from ai_rpg_world.game_world.domain.declaration.time_and_weather import (
    DayNightDeclaration,
    DayPhaseName,
    NoDayNight,
    NoWeather,
    WeatherDeclaration,
)
from ai_rpg_world.game_world.domain.declaration.verb import (
    HappeningNotice,
    InteractionDeclaration,
    NoNotice,
    PerceptionDeclaration,
)
from ai_rpg_world.game_world.domain.design_flaw import DesignFlaw, DesignLocation, DesignWarning
from ai_rpg_world.game_world.domain.effect.effect import Effect
from ai_rpg_world.game_world.domain.value_object.happening_id import HappeningId


def design_location(declaration: str, *ids: Any, field: str) -> DesignLocation:
    return DesignLocation(declaration, "/".join(str(declared_id.value) for declared_id in ids), field)


def duplicate_flaws(declaration: str, keys: Iterable[tuple[Any, ...]], field: str) -> list[DesignFlaw]:
    return [
        DesignFlaw(design_location(declaration, *key, field=field), f"{declaration} is declared more than once")
        for key, count in Counter(keys).items()
        if count > 1
    ]


def one_per_noun_flaws(
    noun: str, verb: str, noun_field: str, declared_nouns: Iterable[Any], nouns_with_verb: list[Any]
) -> list[DesignFlaw]:
    missing = [
        DesignFlaw(design_location(noun, declared, field=verb), f"{noun} has no {verb}")
        for declared in declared_nouns
        if declared not in nouns_with_verb
    ]
    return missing + duplicate_flaws(verb, [(declared,) for declared in nouns_with_verb], noun_field)


@final
@dataclass(frozen=True)
class DeclaredWorldTime:
    has_world_stages: bool
    day_phases: frozenset[DayPhaseName]
    has_day_night: bool
    has_weather: bool

    @classmethod
    def of(
        cls,
        initial_stage: WorldStageDeclaration | NoWorldStages,
        day_night: DayNightDeclaration | NoDayNight,
        weather: WeatherDeclaration | NoWeather,
    ) -> DeclaredWorldTime:
        return cls(
            has_world_stages=not isinstance(initial_stage, NoWorldStages),
            day_phases=(
                frozenset()
                if isinstance(day_night, NoDayNight)
                else frozenset(phase.name for phase in day_night.phases)
            ),
            has_day_night=not isinstance(day_night, NoDayNight),
            has_weather=not isinstance(weather, NoWeather),
        )

    def flaws_of(self, location: DesignLocation, requirements: Requirements) -> list[DesignFlaw]:
        flaws: list[DesignFlaw] = []
        if requirements.reads_world_stage and not self.has_world_stages:
            flaws.append(DesignFlaw(location, "reads the world stage, but this world declares no world stages"))
        if requirements.reads_day_phases and not self.has_day_night:
            flaws.append(DesignFlaw(location, "reads the time of day, but this world declares no day and night"))
        elif undeclared := sorted(phase.value for phase in requirements.reads_day_phases - self.day_phases):
            flaws.append(DesignFlaw(location, f"reads day phases {undeclared} this world does not declare"))
        if requirements.reads_weather and not self.has_weather:
            flaws.append(DesignFlaw(location, "reads the weather, but this world declares no weather"))
        return flaws


class WorldDesignReview:
    def __init__(self, world_time: DeclaredWorldTime) -> None:
        self._world_time = world_time
        self.flaws: list[DesignFlaw] = []
        self.warnings: list[DesignWarning] = []
        self._read: list[tuple[DesignLocation, Requirements]] = []

    def condition(self, placement: RulePlacement, condition: Condition) -> None:
        self.requirements(placement, condition.requirements())

    def precondition(self, placement: RulePlacement, condition: Condition) -> None:
        if not condition.explains_failure():
            self.flaws.append(
                DesignFlaw(placement.location, "the root condition needs a failure_text to tell the actor why")
            )
        self.condition(placement, condition)
        if condition.requirements().may_hide_membership:
            self.warnings.append(
                DesignWarning(
                    placement.location, "reads a membership the actor may not know; trying it reveals the membership"
                )
            )

    def effect(self, placement: RulePlacement, effect: Effect) -> None:
        self.requirements(placement, effect.requirements())

    def requirements(self, placement: RulePlacement, requirements: Requirements) -> None:
        self.flaws += placement.flaws_of(requirements)
        self.flaws += self._world_time.flaws_of(placement.location, requirements)
        self._read.append((placement.location, requirements))

    def perception(self, placement: RulePlacement, perception: PerceptionDeclaration) -> None:
        self.requirements(placement.at_field("perceived_as"), perception.requirements())

    def notice(self, placement: RulePlacement, notice: HappeningNotice | NoNotice) -> None:
        self.requirements(placement, notice.requirements())

    def interaction(self, placement: RulePlacement, interaction: InteractionDeclaration) -> None:
        self.precondition(placement.at_field("precondition"), interaction.precondition)
        self.effect(placement.at_field("effect"), interaction.effect)
        self.perception(placement, interaction.perceived_as)

    def flags(self, declared: Iterable[FlagDeclaration]) -> None:
        raised = self._everything().raises_flags
        for location, requirements in self._read:
            never_raised = sorted(
                flag.flag_id.value
                for flag in requirements.waits_for_flags
                if not flag.initially_raised and flag not in raised
            )
            if never_raised:
                self.flaws.append(
                    DesignFlaw(location, f"waits for flags {never_raised} that start lowered and nothing raises")
                )
        read = self._everything().waits_for_flags
        self.warnings += [
            DesignWarning(design_location("flag", flag.flag_id, field="flag_id"), "is raised but nothing reads it")
            for flag in declared
            if flag in raised and flag not in read
        ]

    def happenings(self, declared: Iterable[HappeningId]) -> None:
        known = frozenset(declared)
        for location, requirements in self._read:
            undeclared = sorted(happening.value for happening in requirements.reads_happenings - known)
            if undeclared:
                self.flaws.append(DesignFlaw(location, f"reads happenings {undeclared} that are not declared"))

    def group_decisions(self, declared: Iterable[GroupDecisionDeclaration]) -> None:
        closed = self._everything().closes_group_decisions
        self.warnings += [
            DesignWarning(
                design_location("group_decision", decision.decision_id, field="decision_id"), "nothing closes it"
            )
            for decision in declared
            if decision not in closed
        ]

    def _everything(self) -> Requirements:
        return reduce(
            Requirements.combined_with, (requirements for _, requirements in self._read), Requirements.nothing()
        )
