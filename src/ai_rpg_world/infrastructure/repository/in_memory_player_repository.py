"""
InMemoryPlayerRepository - プレイヤー関連のインメモリリポジトリ
"""
from typing import List, Optional, Dict, Any
from ai_rpg_world.domain.player.repository.player_repository import PlayerRepository
from .in_memory_repository_base import InMemoryRepositoryBase
from .in_memory_data_store import InMemoryDataStore
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork

# 注意: 旧Playerクラスは廃止予定のため、新集約（Profile, Status, Inventory）への移行が必要です。
# 現状、このリポジトリを参照しているテストはありません。

class InMemoryPlayerRepository(PlayerRepository, InMemoryRepositoryBase):
    """プレイヤーリポジトリ（新集約移行待ち）"""
    
    def __init__(self, data_store: Optional[InMemoryDataStore] = None, unit_of_work: Optional[UnitOfWork] = None):
        super().__init__(data_store, unit_of_work)
    
    @property
    def _players(self) -> Dict[Any, Any]:
        return self._data_store.players

    def find_by_id(self, player_id: Any) -> Optional[Any]:
        pending = self._get_pending_aggregate(player_id)
        if pending is not None:
            return self._clone(pending)
        return self._players.get(player_id)
    
    def find_by_name(self, name: str) -> Optional[Any]:
        for player in self._players.values():
            if hasattr(player, 'name') and player.name == name:
                return player
        return None
    
    def find_by_spot_id(self, spot_id: int) -> List[Any]:
        return [player for player in self._players.values()
                if hasattr(player, 'current_spot_id') and player.current_spot_id == spot_id]
    
    def find_by_battle_id(self, battle_id: int) -> List[Any]:
        return []
    
    def find_by_role(self, role: Any) -> List[Any]:
        return [player for player in self._players.values() if hasattr(player, 'role') and player.role == role]
    
    def save(self, player: Any) -> Any:
        pid = getattr(player, 'player_id', None)
        def operation():
            # IDの取得を試みる（古いPlayerクラスや新しい集約に対応）
            if pid is not None:
                self._players[pid] = player
            return player

        if pid is not None:
            self._register_pending_if_uow(pid, player)
        return self._execute_operation(operation)
    
    def delete(self, player_id: Any) -> bool:
        def operation():
            if player_id in self._players:
                del self._players[player_id]
                return True
            return False
            
        return self._execute_operation(operation)
    
    def find_all(self) -> List[Any]:
        return list(self._players.values())
    
    def exists_by_id(self, player_id: Any) -> bool:
        return player_id in self._players
    
    def exists_by_name(self, name: str) -> bool:
        return any(hasattr(player, 'name') and player.name == name for player in self._players.values())
    
    def count(self) -> int:
        return len(self._players)
    
    def find_by_ids(self, player_ids: List[Any]) -> List[Any]:
        result = []
        for player_id in player_ids:
            player = self._players.get(player_id)
            if player:
                result.append(player)
        return result
    
    def clear(self) -> None:
        self._players.clear()
        self._data_store.next_player_id = 1
    
    def generate_player_id(self) -> int:
        player_id = self._data_store.next_player_id
        self._data_store.next_player_id += 1
        return player_id
