from typing import Dict, List, Optional

from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.repository.monster_repository import MonsterRepository
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_repository_base import InMemoryRepositoryBase


class InMemoryMonsterAggregateRepository(MonsterRepository, InMemoryRepositoryBase):
    """MonsterAggregate用のインメモリ実装"""

    def __init__(
        self,
        data_store: Optional[InMemoryDataStore] = None,
        unit_of_work: Optional[UnitOfWork] = None,
    ):
        super().__init__(data_store, unit_of_work)

    @property
    def _monsters(self) -> Dict[MonsterId, MonsterAggregate]:
        return self._data_store.monsters

    @property
    def _world_object_to_monster_id(self) -> Dict[WorldObjectId, MonsterId]:
        return self._data_store.world_object_to_monster_id

    def find_by_id(self, entity_id: MonsterId) -> Optional[MonsterAggregate]:
        return self._clone(self._monsters.get(entity_id))

    def find_by_ids(self, entity_ids: List[MonsterId]) -> List[MonsterAggregate]:
        return [self._clone(self._monsters[eid]) for eid in entity_ids if eid in self._monsters]

    def find_by_world_object_id(self, world_object_id: WorldObjectId) -> Optional[MonsterAggregate]:
        monster_id = self._world_object_to_monster_id.get(world_object_id)
        if monster_id:
            return self.find_by_id(monster_id)
        return None

    def save(self, entity: MonsterAggregate) -> MonsterAggregate:
        cloned = self._clone(entity)

        def operation():
            # 古いインデックスがあれば削除（world_object_idが変更される可能性を考慮）
            if cloned.monster_id in self._monsters:
                old_monster = self._monsters[cloned.monster_id]
                if old_monster.world_object_id in self._world_object_to_monster_id:
                    del self._world_object_to_monster_id[old_monster.world_object_id]

            self._monsters[cloned.monster_id] = cloned
            self._world_object_to_monster_id[cloned.world_object_id] = cloned.monster_id
            return cloned

        self._register_aggregate(entity)
        return self._execute_operation(operation)

    def delete(self, entity_id: MonsterId) -> bool:
        def operation():
            if entity_id in self._monsters:
                monster = self._monsters[entity_id]
                if monster.world_object_id in self._world_object_to_monster_id:
                    del self._world_object_to_monster_id[monster.world_object_id]
                del self._monsters[entity_id]
                return True
            return False

        return self._execute_operation(operation)

    def find_all(self) -> List[MonsterAggregate]:
        return [self._clone(monster) for monster in self._monsters.values()]
