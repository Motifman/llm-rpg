from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.action.action_outcome_for_actor import ActionOutcomeForActor
from ai_rpg_world.game_world.domain.action.actor_situation import ActorSituation
from ai_rpg_world.game_world.domain.people import TextAboutPeople
from ai_rpg_world.game_world.domain.perception.people_present import PeopleWhoWereThere

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.action_attempt import ActionAttempt
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.declaration.world_design import WorldDesign


@final
@dataclass(frozen=True)
class ActionFixedBeforeEffect:
    situation: ActorSituation
    present: PeopleWhoWereThere
    outcome: ActionOutcomeForActor
    ongoing: TextAboutPeople

    @classmethod
    def of(cls, attempt: ActionAttempt, design: WorldDesign, facts: WorldFacts) -> ActionFixedBeforeEffect:
        situation = ActorSituation.of(attempt, facts)
        return cls(
            situation=situation,
            present=PeopleWhoWereThere.before_the_effect(facts),
            outcome=ActionOutcomeForActor.of_done(attempt, design, situation),
            ongoing=attempt.ongoing_in(design, situation),
        )
