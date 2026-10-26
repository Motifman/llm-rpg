from typing import Any

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.world.value_object.pack_id import PackId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_repository_base import (
    InMemoryRepositoryBase,
    RepositoryUnitOfWorkPort,
)


class InMemoryMonsterAggregateRepository(MonsterRepository, InMemoryRepositoryBase):
    """MonsterAggregate用のインメモリ実装"""

    def __init__(
        self,
        data_store: InMemoryDataStore | None = None,
        unit_of_work: RepositoryUnitOfWorkPort | None = None,
    ):
        super().__init__(data_store, unit_of_work)

    @property
    def _monsters(self) -> dict[MonsterId, MonsterAggregate]:
        return self._data_store.monsters

    def find_by_id(self, entity_id: MonsterId) -> MonsterAggregate | None:
        pending = self._get_pending_aggregate(entity_id)
        if pending is not None:
            cloned: MonsterAggregate | None = self._clone(pending)
            return cloned
        return self._clone(self._monsters.get(entity_id))

    def find_by_ids(self, entity_ids: list[MonsterId]) -> list[MonsterAggregate]:
        return [x for eid in entity_ids for x in [self.find_by_id(eid)] if x is not None]

    def generate_monster_id(self) -> MonsterId:
        """ID発行はリポジトリの責務。"""

        def operation() -> Any:
            mid = MonsterId(self._data_store.next_monster_id)
            self._data_store.next_monster_id += 1
            return mid

        result_value: MonsterId = self._execute_operation(operation)
        return result_value

    def find_by_spot_id(self, spot_id: SpotId) -> list[MonsterAggregate]:
        """指定スポットに紐づくモンスター一覧（ALIVE/DEAD 問わず）。"""
        result = []
        for mid, m in self._monsters.items():
            if m.spot_id == spot_id:
                result.append(self._clone(m))
        return result

    def find_by_pack_id(self, pack_id: PackId) -> list[MonsterAggregate]:
        """指定 pack_id に属するモンスター一覧（ALIVE/DEAD 問わず）。

        Phase 4-O C: pack 援護で同 pack の member を引く用途。
        """
        result = []
        for mid, m in self._monsters.items():
            if m.pack_id is not None and m.pack_id == pack_id:
                result.append(self._clone(m))
        return result

    def save(self, entity: MonsterAggregate) -> MonsterAggregate:
        cloned = self._clone(entity)

        def operation() -> Any:
            self._monsters[cloned.monster_id] = cloned
            return cloned

        self._register_aggregate(entity)
        self._register_pending_if_uow(entity.monster_id, entity)
        result_value: MonsterAggregate = self._execute_operation(operation)
        return result_value

    def delete(self, entity_id: MonsterId) -> bool:
        def operation() -> bool:
            if entity_id in self._monsters:
                del self._monsters[entity_id]
                return True
            return False

        return self._execute_operation(operation)

    def find_all(self) -> list[MonsterAggregate]:
        return [self._clone(monster) for monster in self._monsters.values()]
