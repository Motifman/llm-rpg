"""
餌場の記憶 1 件を表す値オブジェクト。
LRU で最大 N 件保持し、距離が近い順に適用する。
"""

from dataclasses import dataclass

from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate


@dataclass(frozen=True)
class FeedMemoryEntry:
    """餌オブジェクトの位置記憶（object_id と coordinate のペア）"""
    object_id: WorldObjectId
    coordinate: Coordinate
