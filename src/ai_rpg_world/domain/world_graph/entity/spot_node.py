from __future__ import annotations

from dataclasses import dataclass, field
from typing import FrozenSet, Optional, Tuple

from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.exception.map_exception import SpotNameEmptyException
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.value_object.spot_atmosphere import SpotAtmosphere
from ai_rpg_world.domain.world_graph.value_object.trap_def import TrapDef


@dataclass(frozen=True)
class SpotNode:
    """スポットグラフ上の1ノード（メタデータ + 任意で内部構造・雰囲気）

    ``is_intrinsically_dark`` は時刻に依存せず常に暗いスポット（地下室・遮光された
    廃墟内部など）を表す。屋外スポットの「夜だから暗い」は ``is_outdoor`` と
    昼夜サイクルの組み合わせで判定するため、ここでは含めない。

    ``ambient_tags`` は環境音 atlas との交差で発火候補を決めるためのタグ集合。
    例: {"wet", "abandoned", "echoes"}。
    """

    spot_id: SpotId
    name: str
    description: str
    category: SpotCategoryEnum
    parent_id: Optional[SpotId]
    interior: Optional[SpotInterior] = None
    atmosphere: Optional[SpotAtmosphere] = None
    is_outdoor: bool = False
    is_intrinsically_dark: bool = False
    traps: Tuple[TrapDef, ...] = ()
    ambient_tags: FrozenSet[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise SpotNameEmptyException("Spot name cannot be empty")
