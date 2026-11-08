from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.condition.people_selection import PeopleSelection
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.declaration.progress import GroupDecisionDeclaration, WorldStageDeclaration

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates


@final
@dataclass(frozen=True)
class EnterWorldStageEffect:
    stage: WorldStageDeclaration

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.world_stage().enter(self.stage, facts.now())

    def requirements(self) -> Requirements:
        return Requirements.nothing()


@final
@dataclass(frozen=True)
class StartGroupDecisionEffect:
    decision: GroupDecisionDeclaration
    voters: PeopleSelection
    choices: PeopleSelection

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.group_decision(self.decision).start(
            self.voters.select(facts, trigger), self.choices.select(facts, trigger)
        )

    def requirements(self) -> Requirements:
        return self.voters.requirements().combined_with(self.choices.requirements())


@final
@dataclass(frozen=True)
class CloseGroupDecisionEffect:
    decision: GroupDecisionDeclaration

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.group_decision(self.decision).close()

    def requirements(self) -> Requirements:
        return replace(Requirements.nothing(), closes_group_decisions=frozenset({self.decision}))
