from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior


@dataclass(frozen=True)
class ExplorationResult:
    """探索実行の結果"""

    new_interior: SpotInterior
    discovery_descriptions: Tuple[str, ...]
    item_spec_ids_newly_discovered: Tuple[ItemSpecId, ...]
