
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.repository.player_inventory_repository import PlayerInventoryRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.infrastructure.repository.in_memory_repository_base import (
    RepositoryUnitOfWorkPort,
)

from .in_memory_data_store import InMemoryDataStore
from .in_memory_repository_base import InMemoryRepositoryBase


class InMemoryPlayerInventoryRepository(PlayerInventoryRepository, InMemoryRepositoryBase):
    """プレイヤーインベントリリポジトリのインメモリ実装"""
    
    def __init__(self, data_store: InMemoryDataStore | None = None, unit_of_work: RepositoryUnitOfWorkPort | None = None):
        super().__init__(data_store, unit_of_work)
    
    @property
    def _inventories(self) -> dict[PlayerId, PlayerInventoryAggregate]:
        return self._data_store.player_inventories

    def find_by_id(self, player_id: PlayerId) -> PlayerInventoryAggregate | None:
        pending = self._get_pending_aggregate(player_id)
        if pending is not None:
            return self._clone(pending)
        return self._inventories.get(player_id)

    def find_by_ids(self, player_ids: list[PlayerId]) -> list[PlayerInventoryAggregate]:
        return [x for pid in player_ids for x in [self.find_by_id(pid)] if x is not None]

    def save(self, inventory: PlayerInventoryAggregate) -> PlayerInventoryAggregate:
        cloned_inventory = self._clone(inventory)
        def operation():
            self._inventories[cloned_inventory.player_id] = cloned_inventory
            return cloned_inventory

        self._register_aggregate(inventory)
        self._register_pending_if_uow(inventory.player_id, inventory)
        return self._execute_operation(operation)
    
    def delete(self, player_id: PlayerId) -> bool:
        def operation():
            if player_id in self._inventories:
                del self._inventories[player_id]
                return True
            return False
            
        return self._execute_operation(operation)
    
    def find_all(self) -> list[PlayerInventoryAggregate]:
        return list(self._inventories.values())
