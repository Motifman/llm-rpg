from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import Subject
from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration, SpotSectionDeclaration
from ai_rpg_world.game_world.domain.value_object import PersonId
from ai_rpg_world.game_world.domain.whereabouts import DepartedPerson, Occupant, PersonBody

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates


def _occupant_of(person: PersonId, facts: WorldFacts) -> Occupant:
    if facts.rules().departed_persons_act and facts.vitals(person).is_dead():
        return DepartedPerson(person)
    return PersonBody(person)


@final
@dataclass(frozen=True)
class TeleportEffect:
    who: Subject
    to: SpotDeclaration

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.whereabouts().teleport(_occupant_of(self.who.person_in(trigger), facts), self.to)

    def requirements(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class PutIntoSectionEffect:
    who: Subject
    section: SpotSectionDeclaration

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        not_counted = frozenset(person for person in facts.people() if not facts.vitals(person).can_act())
        world.whereabouts().enter_section(_occupant_of(self.who.person_in(trigger), facts), self.section, not_counted)

    def requirements(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class TakeOutOfSectionEffect:
    who: Subject

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.whereabouts().leave_section(_occupant_of(self.who.person_in(trigger), facts))

    def requirements(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class RemoveBodyEffect:
    who: Subject

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.whereabouts().remove(PersonBody(self.who.person_in(trigger)))

    def requirements(self) -> Requirements:
        return self.who.requirements()
