
from typing import Any

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.repository.in_memory_repository_base import (
    RepositoryUnitOfWorkPort,
)

from .in_memory_data_store import InMemoryDataStore
from .in_memory_repository_base import InMemoryRepositoryBase


class InMemoryPlayerStatusRepository(PlayerStatusRepository, InMemoryRepositoryBase):
    """プレイヤーステータスリポジトリのインメモリ実装"""
    
    def __init__(self, data_store: InMemoryDataStore | None = None, unit_of_work: RepositoryUnitOfWorkPort | None = None):
        super().__init__(data_store, unit_of_work)
    
    @property
    def _statuses(self) -> dict[PlayerId, PlayerStatusAggregate]:
        return self._data_store.player_statuses

    def find_by_id(self, player_id: PlayerId) -> PlayerStatusAggregate | None:
        pending = self._get_pending_aggregate(player_id)
        if pending is not None:
            cloned: PlayerStatusAggregate | None = self._clone(pending)
            return cloned
        return self._clone(self._statuses.get(player_id))

    def find_by_ids(self, player_ids: list[PlayerId]) -> list[PlayerStatusAggregate]:
        return [x for pid in player_ids for x in [self.find_by_id(pid)] if x is not None]

    def save(self, status: PlayerStatusAggregate) -> PlayerStatusAggregate:
        cloned_status = self._clone(status)
        def operation() -> Any:
            self._statuses[cloned_status.player_id] = cloned_status
            return cloned_status

        self._register_aggregate(status)
        self._register_pending_if_uow(status.player_id, status)
        result_value: PlayerStatusAggregate = self._execute_operation(operation)
        return result_value
    
    def save_all(self, statuses: list[PlayerStatusAggregate]) -> None:
        """複数のプレイヤーステータスを一括保存"""
        cloned_statuses = [self._clone(s) for s in statuses]
        def operation() -> None:
            for s in cloned_statuses:
                self._statuses[s.player_id] = s
            return None

        for s in statuses:
            self._register_aggregate(s)
            self._register_pending_if_uow(s.player_id, s)
        self._execute_operation(operation)
    
    def delete(self, player_id: PlayerId) -> bool:
        def operation() -> bool:
            if player_id in self._statuses:
                del self._statuses[player_id]
                return True
            return False
            
        return self._execute_operation(operation)
    
    def find_all(self) -> list[PlayerStatusAggregate]:
        return list(self._statuses.values())
