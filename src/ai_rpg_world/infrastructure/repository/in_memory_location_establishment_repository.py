"""
InMemoryLocationEstablishmentRepository - ロケーションスロットのインメモリリポジトリ
"""

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.world.aggregate.location_establishment_aggregate import (
    LocationEstablishmentAggregate,
)
from ai_rpg_world.domain.world.repository.location_establishment_repository import (
    LocationEstablishmentRepository,
)
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.location_slot_id import LocationSlotId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.in_memory_repository_base import (
    RepositoryUnitOfWorkPort,
)

from .in_memory_data_store import InMemoryDataStore
from .in_memory_repository_base import InMemoryRepositoryBase


class InMemoryLocationEstablishmentRepository(
    LocationEstablishmentRepository, InMemoryRepositoryBase
):
    """LocationEstablishment リポジトリのインメモリ実装"""

    def __init__(
        self,
        data_store: InMemoryDataStore | None = None,
        unit_of_work: RepositoryUnitOfWorkPort | None = None,
    ):
        super().__init__(data_store, unit_of_work)

    @property
    def _location_establishments(
        self,
    ) -> dict[LocationSlotId, LocationEstablishmentAggregate]:
        return self._data_store.location_establishments

    def find_by_id(
        self, slot_id: LocationSlotId
    ) -> LocationEstablishmentAggregate | None:
        pending = self._get_pending_aggregate(slot_id)
        if pending is not None:
            return self._clone(pending)
        return self._clone(self._location_establishments.get(slot_id))

    def find_by_spot_and_location(
        self,
        spot_id: SpotId,
        location_area_id: LocationAreaId,
    ) -> LocationEstablishmentAggregate | None:
        slot_id = LocationSlotId(spot_id=spot_id, location_area_id=location_area_id)
        return self.find_by_id(slot_id)

    def find_by_ids(
        self, slot_ids: list[LocationSlotId]
    ) -> list[LocationEstablishmentAggregate]:
        return [
            x
            for sid in slot_ids
            for x in [self.find_by_id(sid)]
            if x is not None
        ]

    def save(self, slot: LocationEstablishmentAggregate) -> LocationEstablishmentAggregate:
        cloned = self._clone(slot)

        def operation():
            self._location_establishments[cloned.id] = cloned
            return cloned

        self._register_aggregate(slot)
        self._register_pending_if_uow(slot.id, slot)
        return self._execute_operation(operation)

    def delete(self, slot_id: LocationSlotId) -> bool:
        def operation():
            if slot_id in self._location_establishments:
                del self._location_establishments[slot_id]
                return True
            return False

        return self._execute_operation(operation)

    def find_all(self) -> list[LocationEstablishmentAggregate]:
        return [self._clone(s) for s in self._location_establishments.values()]
