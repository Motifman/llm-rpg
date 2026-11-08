from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.declaration.progress import GroupDecisionDeclaration, WorldStageDeclaration
from ai_rpg_world.game_world.domain.effect.declared_group_decision_rules import DeclaredGroupDecisionRules

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
    rules: DeclaredGroupDecisionRules

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.group_decision(self.rules.decision).start(
            self.rules.voters.select(facts, trigger), self.rules.choices.select(facts, trigger)
        )

    def requirements(self) -> Requirements:
        return self.rules.voters.requirements().combined_with(self.rules.choices.requirements())


@final
@dataclass(frozen=True)
class CloseGroupDecisionEffect:
    decision: GroupDecisionDeclaration

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.group_decision(self.decision).close()

    def requirements(self) -> Requirements:
        return replace(Requirements.nothing(), closes_group_decisions=frozenset({self.decision}))
