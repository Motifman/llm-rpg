from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.exception.map_exception import SpotNameEmptyException
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


@dataclass(frozen=True)
class SpotNode:
    """スポットグラフ上の1ノード（Step1: メタデータのみ。内部構造は Step2）"""

    spot_id: SpotId
    name: str
    description: str
    category: SpotCategoryEnum
    parent_id: Optional[SpotId]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise SpotNameEmptyException("Spot name cannot be empty")
