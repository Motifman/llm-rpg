
from typing import Any

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.repository.spot_repository import SpotRepository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.in_memory_repository_base import (
    RepositoryUnitOfWorkPort,
)

from .in_memory_data_store import InMemoryDataStore
from .in_memory_repository_base import InMemoryRepositoryBase


class InMemorySpotRepository(SpotRepository, InMemoryRepositoryBase):
    """スポットリポジトリのインメモリ実装"""

    def __init__(self, data_store: InMemoryDataStore | None = None, unit_of_work: RepositoryUnitOfWorkPort | None = None):
        super().__init__(data_store, unit_of_work)

    @property
    def _spot_dict(self) -> dict[SpotId, Spot]:
        return self._data_store.spots

    def find_by_id(self, spot_id: SpotId) -> Spot | None:
        pending = self._get_pending_aggregate(spot_id)
        if pending is not None:
            cloned: Spot | None = self._clone(pending)
            return cloned
        return self._clone(self._spot_dict.get(spot_id))

    def find_by_ids(self, spot_ids: list[SpotId]) -> list[Spot]:
        return [s for sid in spot_ids for s in [self.find_by_id(sid)] if s is not None]

    def save(self, spot: Spot) -> Spot:
        cloned = self._clone(spot)
        def operation() -> Any:
            self._spot_dict[cloned.spot_id] = cloned
            return cloned

        self._register_pending_if_uow(spot.spot_id, spot)
        result_value: Spot = self._execute_operation(operation)
        return result_value

    def delete(self, spot_id: SpotId) -> bool:
        def operation() -> bool:
            if spot_id in self._spot_dict:
                del self._spot_dict[spot_id]
                return True
            return False

        return self._execute_operation(operation)

    def find_all(self) -> list[Spot]:
        return [self._clone(s) for s in self._spot_dict.values()]

    def find_by_name(self, name: str) -> Spot | None:
        """名前でスポットを検索。find_all をループして name でマッチする最初のものを返す。"""
        if not name or not isinstance(name, str):
            return None
        key = name.strip()
        for spot in self._spot_dict.values():
            if spot.name == key:
                return self._clone(spot)
        return None
