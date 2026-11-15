from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, final

from ai_rpg_world.game_world.domain.declaration.object_and_item import ItemSpecDeclaration
from ai_rpg_world.game_world.domain.effect.effect import Effect

if TYPE_CHECKING:
    from ai_rpg_world.game_world.domain.action.trigger import Trigger
    from ai_rpg_world.game_world.domain.condition.world_facts import WorldFacts
    from ai_rpg_world.game_world.domain.effect.world_aggregates import WorldAggregates


@final
@dataclass(frozen=True)
class ItemUseDeclaration:
    item_spec: ItemSpecDeclaration
    effect: Effect

    def apply(self, facts: WorldFacts, world: WorldAggregates, trigger: Trigger) -> None:
        self.effect.apply(facts, world, trigger)
