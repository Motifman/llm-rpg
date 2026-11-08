from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from ai_rpg_world.game_world.domain.condition.requirements import Requirements

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates


class Effect(Protocol):
    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None: ...

    def requirements(self) -> Requirements: ...
