from typing import List, Optional, Dict
from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from .in_memory_repository_base import InMemoryRepositoryBase
from .in_memory_data_store import InMemoryDataStore
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork


class InMemorySpotRepository(SpotRepository, InMemoryRepositoryBase):
    """スポットリポジトリのインメモリ実装"""

    def __init__(self, data_store: Optional[InMemoryDataStore] = None, unit_of_work: Optional[UnitOfWork] = None):
        super().__init__(data_store, unit_of_work)

    @property
    def _spot_dict(self) -> Dict[SpotId, Spot]:
        return self._data_store.spots

    def find_by_id(self, spot_id: SpotId) -> Optional[Spot]:
        pending = self._get_pending_aggregate(spot_id)
        if pending is not None:
            return self._clone(pending)
        return self._clone(self._spot_dict.get(spot_id))

    def find_by_ids(self, spot_ids: List[SpotId]) -> List[Spot]:
        return [s for sid in spot_ids for s in [self.find_by_id(sid)] if s is not None]

    def save(self, spot: Spot) -> Spot:
        cloned = self._clone(spot)
        def operation():
            self._spot_dict[cloned.spot_id] = cloned
            return cloned

        self._register_pending_if_uow(spot.spot_id, spot)
        return self._execute_operation(operation)

    def delete(self, spot_id: SpotId) -> bool:
        def operation():
            if spot_id in self._spot_dict:
                del self._spot_dict[spot_id]
                return True
            return False

        return self._execute_operation(operation)

    def find_all(self) -> List[Spot]:
        return [self._clone(s) for s in self._spot_dict.values()]
