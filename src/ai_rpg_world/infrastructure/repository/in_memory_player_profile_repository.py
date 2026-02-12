from typing import List, Optional, Dict
from ai_rpg_world.domain.player.repository.player_profile_repository import PlayerProfileRepository
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import PlayerProfileAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from .in_memory_repository_base import InMemoryRepositoryBase
from .in_memory_data_store import InMemoryDataStore
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork


class InMemoryPlayerProfileRepository(PlayerProfileRepository, InMemoryRepositoryBase):
    """プレイヤープロフィールリポジトリのインメモリ実装"""
    
    def __init__(self, data_store: Optional[InMemoryDataStore] = None, unit_of_work: Optional[UnitOfWork] = None):
        super().__init__(data_store, unit_of_work)
    
    @property
    def _profiles(self) -> Dict[PlayerId, PlayerProfileAggregate]:
        return self._data_store.player_profiles

    def find_by_id(self, player_id: PlayerId) -> Optional[PlayerProfileAggregate]:
        return self._profiles.get(player_id)
    
    def find_by_ids(self, player_ids: List[PlayerId]) -> List[PlayerProfileAggregate]:
        return [self._profiles[pid] for pid in player_ids if pid in self._profiles]
    
    def find_by_name(self, name: PlayerName) -> Optional[PlayerProfileAggregate]:
        for profile in self._profiles.values():
            if profile.name == name:
                return profile
        return None

    def exists_name(self, name: PlayerName) -> bool:
        return any(profile.name == name for profile in self._profiles.values())

    def save(self, profile: PlayerProfileAggregate) -> PlayerProfileAggregate:
        cloned_profile = self._clone(profile)
        def operation():
            self._profiles[cloned_profile.player_id] = cloned_profile
            return cloned_profile
            
        self._register_aggregate(profile)
        return self._execute_operation(operation)
    
    def delete(self, player_id: PlayerId) -> bool:
        def operation():
            if player_id in self._profiles:
                del self._profiles[player_id]
                return True
            return False
            
        return self._execute_operation(operation)
    
    def find_all(self) -> List[PlayerProfileAggregate]:
        return list(self._profiles.values())

    def generate_id(self) -> PlayerId:
        player_id = self._data_store.next_player_id
        self._data_store.next_player_id += 1
        return PlayerId(player_id)
