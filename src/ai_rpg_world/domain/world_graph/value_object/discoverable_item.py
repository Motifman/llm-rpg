from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.value_object.discovery_condition import DiscoveryCondition


@dataclass(frozen=True)
class DiscoverableItem:
    item_spec_id: ItemSpecId
    discovery_condition: DiscoveryCondition
    is_discovered: bool = False
    description: str = ""

    def mark_discovered(self) -> DiscoverableItem:
        if self.is_discovered:
            return self
        return DiscoverableItem(
            item_spec_id=self.item_spec_id,
            discovery_condition=self.discovery_condition,
            is_discovered=True,
            description=self.description,
        )
