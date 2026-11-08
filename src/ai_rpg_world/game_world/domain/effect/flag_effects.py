from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.condition.requirements import Requirements
from ai_rpg_world.game_world.domain.declaration.progress import FlagDeclaration

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates


@final
@dataclass(frozen=True)
class RaiseFlagEffect:
    flag: FlagDeclaration

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.flags().raise_flag(self.flag, trigger)

    def requirements(self) -> Requirements:
        return replace(Requirements.nothing(), raises_flags=frozenset({self.flag}))


@final
@dataclass(frozen=True)
class LowerFlagEffect:
    flag: FlagDeclaration

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        world.flags().lower_flag(self.flag, trigger)

    def requirements(self) -> Requirements:
        return Requirements.nothing()
