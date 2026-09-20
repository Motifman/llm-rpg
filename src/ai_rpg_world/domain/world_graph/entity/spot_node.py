from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.exception.map_exception import SpotNameEmptyException
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import SpotAtmosphere
from ai_rpg_world.domain.world_graph.value_object.spot_position import SpotPosition
from ai_rpg_world.domain.world_graph.value_object.trap_def import TrapDef


@dataclass(frozen=True)
class SpotNode:
    """スポットグラフ上の1ノード（メタデータ + 任意で内部構造・雰囲気）"""

    spot_id: SpotId
    name: str
    description: str
    category: SpotCategoryEnum
    parent_id: SpotId | None
    interior: SpotInterior | None = None
    atmosphere: SpotAtmosphere | None = None
    is_outdoor: bool = False
    traps: tuple[TrapDef, ...] = ()
    position: SpotPosition | None = None
    area_id: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise SpotNameEmptyException("Spot name cannot be empty")
