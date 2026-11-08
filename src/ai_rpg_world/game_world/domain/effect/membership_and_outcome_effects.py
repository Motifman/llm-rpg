from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.subject import Subject
from ai_rpg_world.game_world.domain.declaration.character import GroupDeclaration
from ai_rpg_world.game_world.domain.declaration.progress import OutcomeDeclaration
from ai_rpg_world.game_world.domain.person import DeclaredOutcome
from ai_rpg_world.game_world.domain.whereabouts import PersonBody

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates


@final
@dataclass(frozen=True)
class JoinGroupEffect:
    who: Subject
    group: GroupDeclaration

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.membership().join(self.who.person_in(trigger), self.group)

    def requirements(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class LeaveGroupEffect:
    who: Subject
    group: GroupDeclaration

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.membership().leave(self.who.person_in(trigger), self.group)

    def requirements(self) -> Requirements:
        return self.who.requirements()


@final
@dataclass(frozen=True)
class SetOutcomeEffect:
    who: Subject
    outcome: OutcomeDeclaration

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        person = self.who.person_in(trigger)
        world.outcomes().decide(person, DeclaredOutcome(self.outcome))
        world.whereabouts().remove(PersonBody(person))

    def requirements(self) -> Requirements:
        return self.who.requirements()
