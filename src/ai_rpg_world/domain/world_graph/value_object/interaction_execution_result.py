from __future__ import annotations

from dataclasses import dataclass
from typing import FrozenSet, Tuple

from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId


@dataclass(frozen=True)
class InteractionExecutionResult:
    """インタラクション適用後のスナップショット（ドメインサービスが返す）"""

    new_interior: SpotInterior
    new_flags: FrozenSet[str]
    messages: Tuple[str, ...]
    item_spec_ids_to_grant: Tuple[ItemSpecId, ...]
    item_spec_ids_to_remove: Tuple[ItemSpecId, ...]
    connection_passability_updates: Tuple[Tuple[ConnectionId, bool], ...]
