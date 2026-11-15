from __future__ import annotations

from typing import TYPE_CHECKING

from ai_rpg_world.game_world.domain.perception.perceiver import Perceiver
from ai_rpg_world.game_world.domain.person.person_outcomes import DeclaredOutcome
from ai_rpg_world.game_world.domain.value_object import PersonId

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts


def perceiver_in_world(facts: WorldFacts, person: PersonId, attentive: bool) -> Perceiver:
    vitals = facts.vitals(person)
    # 作者の結末が決まった人は世界から外れていて、居場所が無い。
    if isinstance(facts.outcomes().outcome_of(person), DeclaredOutcome):
        return vitals.perceiver_after_leaving()
    departed_persons_act = facts.rules().departed_persons_act
    location = facts.whereabouts().location_of(vitals.occupant_in_world(departed_persons_act))
    return vitals.perceiver_at(location, departed_persons_act, attentive=attentive)
