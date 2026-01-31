from typing import List, Optional, Dict
from ai_rpg_world.domain.player.repository.player_inventory_repository import PlayerInventoryRepository
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from .in_memory_repository_base import InMemoryRepositoryBase
from .in_memory_data_store import InMemoryDataStore
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork


class InMemoryPlayerInventoryRepository(PlayerInventoryRepository, InMemoryRepositoryBase):
    """プレイヤーインベントリリポジトリのインメモリ実装"""
    
    def __init__(self, data_store: Optional[InMemoryDataStore] = None, unit_of_work: Optional[UnitOfWork] = None):
        super().__init__(data_store, unit_of_work)
    
    @property
    def _inventories(self) -> Dict[PlayerId, PlayerInventoryAggregate]:
        return self._data_store.player_inventories

    def find_by_id(self, player_id: PlayerId) -> Optional[PlayerInventoryAggregate]:
        return self._inventories.get(player_id)
    
    def find_by_ids(self, player_ids: List[PlayerId]) -> List[PlayerInventoryAggregate]:
        return [self._inventories[pid] for pid in player_ids if pid in self._inventories]
    
    def save(self, inventory: PlayerInventoryAggregate) -> PlayerInventoryAggregate:
        def operation():
            self._inventories[inventory.player_id] = inventory
            return inventory
            
        return self._execute_operation(operation)
    
    def delete(self, player_id: PlayerId) -> bool:
        def operation():
            if player_id in self._inventories:
                del self._inventories[player_id]
                return True
            return False
            
        return self._execute_operation(operation)
    
    def find_all(self) -> List[PlayerInventoryAggregate]:
        return list(self._inventories.values())
