from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.condition.condition import NoText
from ai_rpg_world.game_world.domain.condition.leaf_condition import LeafCondition
from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import Subject
from ai_rpg_world.game_world.domain.declaration.object_and_item import ItemSpecDeclaration
from ai_rpg_world.game_world.domain.declaration.spot import SpotDeclaration, SpotSectionDeclaration
from ai_rpg_world.game_world.domain.people import TextWithUnassignedPeople
from ai_rpg_world.game_world.domain.person import Died, Down, Outcome
from ai_rpg_world.game_world.domain.value_object import Count, FatigueAmount, Gold, HungerAmount, PersonId
from ai_rpg_world.game_world.domain.whereabouts import AtSpot, DepartedPerson, Occupant, PersonBody

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts


def _occupant_of(person: PersonId, facts: WorldFacts) -> Occupant:
    return facts.vitals(person).occupant_in_world(facts.rules().departed_persons_act)


@final
@dataclass(frozen=True)
class HasItemCondition(LeafCondition):
    who: Subject
    item_spec: ItemSpecDeclaration
    count: Count
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return facts.inventory(self.who.person_in(trigger)).count_of(self.item_spec.item_spec_id) >= self.count

    def _requirements_besides_text(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class IsHoldingCondition(LeafCondition):
    who: Subject
    item_spec: ItemSpecDeclaration
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return any(
            facts.item(item).spec_id == self.item_spec.item_spec_id
            for item in facts.inventory(self.who.person_in(trigger)).held_items()
        )

    def _requirements_besides_text(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class GoldAtLeastCondition(LeafCondition):
    who: Subject
    amount: Gold
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return facts.inventory(self.who.person_in(trigger)).available_gold() >= self.amount

    def _requirements_besides_text(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class IsAtSpotCondition(LeafCondition):
    who: Subject
    spot: SpotDeclaration
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return facts.whereabouts().is_at(_occupant_of(self.who.person_in(trigger), facts), self.spot)

    def _requirements_besides_text(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class IsInSectionCondition(LeafCondition):
    who: Subject
    section: SpotSectionDeclaration
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return facts.whereabouts().is_in_section(_occupant_of(self.who.person_in(trigger), facts), self.section)

    def _requirements_besides_text(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class SearchCountAtLeastCondition(LeafCondition):
    who: Subject
    count: Count
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        person = self.who.person_in(trigger)
        location = facts.whereabouts().location_of(_occupant_of(person, facts))
        if not isinstance(location, AtSpot):
            return False
        return facts.search_progress(location.spot).search_count(person) >= self.count

    def _requirements_besides_text(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class IsDownCondition(LeafCondition):
    who: Subject
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return isinstance(facts.vitals(self.who.person_in(trigger)).life_state(), Down)

    def _requirements_besides_text(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class IsAliveCondition(LeafCondition):
    who: Subject
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return not facts.vitals(self.who.person_in(trigger)).is_dead()

    def _requirements_besides_text(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class HungerAtLeastCondition(LeafCondition):
    who: Subject
    value: HungerAmount
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return facts.vitals(self.who.person_in(trigger)).hunger() >= self.value

    def _requirements_besides_text(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class FatigueAtLeastCondition(LeafCondition):
    who: Subject
    value: FatigueAmount
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return facts.vitals(self.who.person_in(trigger)).fatigue() >= self.value

    def _requirements_besides_text(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class OutcomeIsCondition(LeafCondition):
    who: Subject
    outcome: Outcome
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return facts.outcomes().outcome_of(self.who.person_in(trigger)) == self.outcome

    def _requirements_besides_text(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class AllOutcomesDecidedCondition(LeafCondition):
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return facts.outcomes().all_decided()

    def _requirements_besides_text(self) -> Requirements:
        return Requirements.nothing()


@final
@dataclass(frozen=True)
class PeopleCountAtLeastCondition(LeafCondition):
    people: PeopleSelection
    count: Count
    failure_text: TextWithUnassignedPeople | NoText

    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return Count(len(self.people.select(facts, trigger))) >= self.count

    def _requirements_besides_text(self) -> Requirements:
        return self.people.requirements()
