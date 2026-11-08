from __future__ import annotations

from dataclasses import dataclass
from typing import final

from ai_rpg_world.game_world.domain.action.trigger import Trigger
from ai_rpg_world.game_world.domain.condition.condition import FailureReason, HiddenFailure
from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates


@final
@dataclass(frozen=True)
class AlwaysHolds:
    def holds(self, facts: WorldFacts, trigger: Trigger) -> bool:
        return True

    def requirements(self) -> Requirements:
        return Requirements.nothing()

    def failure_reason(self, facts: WorldFacts, trigger: Trigger) -> FailureReason | HiddenFailure | None:
        return None

    def explains_failure(self) -> bool:
        return True


@final
@dataclass(frozen=True)
class ChangesNothing:
    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        return None

    def requirements(self) -> Requirements:
        return Requirements.nothing()
