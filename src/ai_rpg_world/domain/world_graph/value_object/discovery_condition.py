from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.enum.discovery_condition_type import DiscoveryConditionTypeEnum


@dataclass(frozen=True)
class DiscoveryCondition:
    condition_type: DiscoveryConditionTypeEnum
    required_search_count: int = 1
    required_item_spec_id: Optional[ItemSpecId] = None
    flag_name: Optional[str] = None

    def __post_init__(self) -> None:
        if self.required_search_count < 1:
            raise ValueError("required_search_count must be >= 1")
