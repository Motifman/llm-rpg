from typing import List, Optional, Dict
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from .in_memory_repository_base import InMemoryRepositoryBase
from .in_memory_data_store import InMemoryDataStore
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork

class InMemoryPhysicalMapRepository(PhysicalMapRepository, InMemoryRepositoryBase):
    """物理マップリポジトリのインメモリ実装"""
    
    def __init__(self, data_store: Optional[InMemoryDataStore] = None, unit_of_work: Optional[UnitOfWork] = None):
        super().__init__(data_store, unit_of_work)
    
    @property
    def _maps(self) -> Dict[SpotId, PhysicalMapAggregate]:
        return self._data_store.physical_maps

    def find_by_id(self, entity_id: SpotId) -> Optional[PhysicalMapAggregate]:
        return self._clone(self._maps.get(entity_id))
    
    def find_by_spot_id(self, spot_id: SpotId) -> Optional[PhysicalMapAggregate]:
        return self.find_by_id(spot_id)

    def find_by_ids(self, entity_ids: List[SpotId]) -> List[PhysicalMapAggregate]:
        return [self._clone(self._maps[sid]) for sid in entity_ids if sid in self._maps]
    
    def save(self, physical_map: PhysicalMapAggregate) -> PhysicalMapAggregate:
        cloned_map = self._clone(physical_map)
        def operation():
            self._maps[cloned_map.spot_id] = cloned_map
            return cloned_map
            
        return self._execute_operation(operation)
    
    def delete(self, spot_id: SpotId) -> bool:
        def operation():
            if spot_id in self._maps:
                del self._maps[spot_id]
                return True
            return False
            
        return self._execute_operation(operation)
    
    def find_all(self) -> List[PhysicalMapAggregate]:
        return list(self._maps.values())
