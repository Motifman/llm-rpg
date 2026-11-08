from __future__ import annotations

from dataclasses import dataclass, replace
from functools import reduce
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.action.trigger import EachPersonOf
from ai_rpg_world.game_world.domain.condition.condition import Condition
from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import SubjectKind
from ai_rpg_world.game_world.domain.effect.effect import Effect
from ai_rpg_world.game_world.domain.effect.weight import Weight
from ai_rpg_world.game_world.domain.exception.effect_exception import NoBranchesException
from ai_rpg_world.game_world.domain.value_object import PersonId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates


def _all_of(requirements: tuple[Requirements, ...]) -> Requirements:
    return reduce(Requirements.combined_with, requirements, Requirements.nothing())


def _with_chance(requirements: Requirements) -> Requirements:
    return replace(requirements, uses_chance=True)


# frozenset の並びは実行ごとに変わるので、偶然で選ぶ人が実行ごとにずれないよう世界の並びに従う
def _in_world_order(selected: frozenset[PersonId], facts: WorldFacts) -> tuple[PersonId, ...]:
    return tuple(person for person in facts.people() if person in selected)


@final
@dataclass(frozen=True)
class NoEffect:
    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        pass

    def requirements(self) -> Requirements:
        return Requirements.nothing()


@final
@dataclass(frozen=True)
class SequenceEffect:
    steps: tuple[Effect, ...]

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        for step in self.steps:
            step.apply(facts, world, trigger)

    def requirements(self) -> Requirements:
        return _all_of(tuple(step.requirements() for step in self.steps))


@final
@dataclass(frozen=True)
class ConditionalEffect:
    condition: Condition
    then: Effect
    otherwise: Effect | NoEffect

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        chosen = self.then if self.condition.holds(facts, trigger) else self.otherwise
        chosen.apply(facts, world, trigger)

    def requirements(self) -> Requirements:
        return _all_of((self.condition.requirements(), self.then.requirements(), self.otherwise.requirements()))


@final
@dataclass(frozen=True)
class RandomBranchEffect:
    branches: tuple[tuple[Weight, Effect], ...]

    def __post_init__(self) -> None:
        if not self.branches:
            raise NoBranchesException("RandomBranchEffect needs at least one branch")

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        point = facts.random().next_fraction() * sum(weight.value for weight, _ in self.branches)
        reached = 0
        for weight, effect in self.branches:
            reached += weight.value
            if point < reached:
                effect.apply(facts, world, trigger)
                return

    def requirements(self) -> Requirements:
        return _with_chance(_all_of(tuple(effect.requirements() for _, effect in self.branches)))


@final
@dataclass(frozen=True)
class ForEveryoneEffect:
    people: PeopleSelection
    effect: Effect

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        for person in _in_world_order(self.people.select(facts, trigger), facts):
            self.effect.apply(facts, world, EachPersonOf(trigger, person))

    def requirements(self) -> Requirements:
        return self.people.requirements().combined_with(
            self.effect.requirements().without_subject(SubjectKind.EACH_PERSON)
        )


@final
@dataclass(frozen=True)
class ForSomeoneEffect:
    people: PeopleSelection
    effect: Effect

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        candidates = _in_world_order(self.people.select(facts, trigger), facts)
        if not candidates:
            return
        chosen = candidates[int(facts.random().next_fraction() * len(candidates))]
        self.effect.apply(facts, world, EachPersonOf(trigger, chosen))

    def requirements(self) -> Requirements:
        return _with_chance(
            self.people.requirements().combined_with(
                self.effect.requirements().without_subject(SubjectKind.EACH_PERSON)
            )
        )
