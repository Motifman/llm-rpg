from __future__ import annotations

from typing import Dict, Optional

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import ISpotInteriorRepository


class InMemorySpotInteriorRepository(ISpotInteriorRepository):
    """テスト・デモ用のインメモリスポット内部リポジトリ。"""

    def __init__(self, data: Optional[Dict[SpotId, SpotInterior]] = None) -> None:
        self._data: Dict[SpotId, SpotInterior] = dict(data or {})

    def find_by_spot_id(self, spot_id: SpotId) -> Optional[SpotInterior]:
        return self._data.get(spot_id)

    def save(self, spot_id: SpotId, interior: SpotInterior) -> None:
        self._data[spot_id] = interior
