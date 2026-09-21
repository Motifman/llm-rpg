
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId

from .in_memory_data_store import InMemoryDataStore
from .in_memory_repository_base import InMemoryRepositoryBase


class InMemoryPhysicalMapRepository(PhysicalMapRepository, InMemoryRepositoryBase):
    """物理マップリポジトリのインメモリ実装"""
    
    def __init__(self, data_store: InMemoryDataStore | None = None, unit_of_work: UnitOfWork | None = None):
        super().__init__(data_store, unit_of_work)
    
    @property
    def _maps(self) -> dict[SpotId, PhysicalMapAggregate]:
        return self._data_store.physical_maps

    def find_by_id(self, entity_id: SpotId) -> PhysicalMapAggregate | None:
        pending = self._get_pending_aggregate(entity_id)
        if pending is not None:
            return self._clone(pending)
        return self._clone(self._maps.get(entity_id))

    def find_by_spot_id(self, spot_id: SpotId) -> PhysicalMapAggregate | None:
        return self.find_by_id(spot_id)

    def find_by_ids(self, entity_ids: list[SpotId]) -> list[PhysicalMapAggregate]:
        return [x for sid in entity_ids for x in [self.find_by_id(sid)] if x is not None]
    
    def save(self, physical_map: PhysicalMapAggregate) -> PhysicalMapAggregate:
        cloned_map = self._clone(physical_map)
        index = self._data_store.world_object_id_to_spot_id

        def operation():
            old_map = self._maps.get(cloned_map.spot_id)
            if old_map is not None:
                for obj in old_map.get_all_objects():
                    if obj.object_id in index:
                        del index[obj.object_id]
            for obj in cloned_map.get_all_objects():
                index[obj.object_id] = cloned_map.spot_id
            self._maps[cloned_map.spot_id] = cloned_map
            return cloned_map

        self._register_aggregate(physical_map)
        self._register_pending_if_uow(physical_map.spot_id, physical_map)
        return self._execute_operation(operation)

    def delete(self, spot_id: SpotId) -> bool:
        index = self._data_store.world_object_id_to_spot_id

        def operation():
            if spot_id not in self._maps:
                return False
            old_map = self._maps[spot_id]
            for obj in old_map.get_all_objects():
                if obj.object_id in index:
                    del index[obj.object_id]
            del self._maps[spot_id]
            return True

        return self._execute_operation(operation)
    
    def find_all(self) -> list[PhysicalMapAggregate]:
        return list(self._maps.values())

    def generate_world_object_id(self) -> WorldObjectId:
        """設置オブジェクト・落ちアイテム用の新規 WorldObjectId を発行する"""
        wid = WorldObjectId(self._data_store.next_world_object_id)
        self._data_store.next_world_object_id += 1
        return wid

    def find_spot_id_by_object_id(self, object_id: WorldObjectId) -> SpotId | None:
        """指定した WorldObjectId が配置されているスポットIDを返す。O(1) のインデックス参照。"""
        return self._data_store.world_object_id_to_spot_id.get(object_id)
