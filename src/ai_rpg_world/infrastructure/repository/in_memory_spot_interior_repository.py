from __future__ import annotations

from typing import Dict, Optional, TYPE_CHECKING

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.repository.spot_interior_repository import (
    ISpotInteriorRepository,
)

if TYPE_CHECKING:
    from ai_rpg_world.infrastructure.repository.in_memory_data_store import (
        InMemoryDataStore,
    )


class InMemorySpotInteriorRepository(ISpotInteriorRepository):
    """テスト・デモ用のインメモリスポット内部リポジトリ。"""

    def __init__(
        self,
        data: Optional[Dict[SpotId, SpotInterior]] = None,
        *,
        data_store: Optional["InMemoryDataStore"] = None,
    ) -> None:
        if data is not None and data_store is not None:
            raise ValueError("dataとdata_storeは同時に指定できません")
        self._data_store = data_store
        self._standalone_data: Dict[SpotId, SpotInterior] = dict(data or {})

    @property
    def _data(self) -> Dict[SpotId, SpotInterior]:
        if self._data_store is not None:
            return self._data_store.spot_interiors
        return self._standalone_data

    def find_by_spot_id(self, spot_id: SpotId) -> Optional[SpotInterior]:
        return self._data.get(spot_id)

    def save(self, spot_id: SpotId, interior: SpotInterior) -> None:
        self._data[spot_id] = interior
