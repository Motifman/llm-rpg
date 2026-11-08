from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import Subject
from ai_rpg_world.game_world.domain.value_object import Damage, FatigueAmount, HealAmount, HungerAmount, Rate

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates


@final
@dataclass(frozen=True)
class DamageEffect:
    who: Subject
    amount: Damage

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        victim = self.who.person_in(trigger)
        world.vitals(victim).take_damage(self.amount, facts.now(), trigger.fall_cause_for(victim))

    def requirements(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class HealEffect:
    who: Subject
    amount: HealAmount

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.vitals(self.who.person_in(trigger)).heal(self.amount)

    def requirements(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class ReviveEffect:
    who: Subject
    hp_rate: Rate

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.vitals(self.who.person_in(trigger)).revive(self.hp_rate, facts.now())

    def requirements(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class SatisfyHungerEffect:
    who: Subject
    amount: HungerAmount

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.vitals(self.who.person_in(trigger)).satisfy_hunger(self.amount, facts.rules().hunger)

    def requirements(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class RestEffect:
    who: Subject
    amount: FatigueAmount

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.vitals(self.who.person_in(trigger)).rest(self.amount, facts.rules().fatigue)

    def requirements(self) -> Requirements:
        return self.who.requirements()
