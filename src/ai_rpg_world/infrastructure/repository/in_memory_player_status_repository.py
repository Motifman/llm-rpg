from typing import List, Optional, Dict
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from .in_memory_repository_base import InMemoryRepositoryBase
from .in_memory_data_store import InMemoryDataStore
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork


class InMemoryPlayerStatusRepository(PlayerStatusRepository, InMemoryRepositoryBase):
    """プレイヤーステータスリポジトリのインメモリ実装"""
    
    def __init__(self, data_store: Optional[InMemoryDataStore] = None, unit_of_work: Optional[UnitOfWork] = None):
        super().__init__(data_store, unit_of_work)
    
    @property
    def _statuses(self) -> Dict[PlayerId, PlayerStatusAggregate]:
        return self._data_store.player_statuses

    def find_by_id(self, player_id: PlayerId) -> Optional[PlayerStatusAggregate]:
        return self._statuses.get(player_id)
    
    def find_by_ids(self, player_ids: List[PlayerId]) -> List[PlayerStatusAggregate]:
        return [self._statuses[pid] for pid in player_ids if pid in self._statuses]
    
    def save(self, status: PlayerStatusAggregate) -> PlayerStatusAggregate:
        def operation():
            self._statuses[status.player_id] = status
            return status
            
        return self._execute_operation(operation)
    
    def delete(self, player_id: PlayerId) -> bool:
        def operation():
            if player_id in self._statuses:
                del self._statuses[player_id]
                return True
            return False
            
        return self._execute_operation(operation)
    
    def find_all(self) -> List[PlayerStatusAggregate]:
        return list(self._statuses.values())
