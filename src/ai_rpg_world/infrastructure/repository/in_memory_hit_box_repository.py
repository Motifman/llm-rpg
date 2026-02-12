from typing import Dict, List, Optional

from ai_rpg_world.domain.combat.aggregate.hit_box_aggregate import HitBoxAggregate
from ai_rpg_world.domain.combat.repository.hit_box_repository import HitBoxRepository
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from .in_memory_data_store import InMemoryDataStore
from .in_memory_repository_base import InMemoryRepositoryBase


class InMemoryHitBoxRepository(HitBoxRepository, InMemoryRepositoryBase):
    """HitBoxリポジトリのインメモリ実装"""

    def __init__(
        self,
        data_store: Optional[InMemoryDataStore] = None,
        unit_of_work: Optional[UnitOfWork] = None,
    ):
        super().__init__(data_store, unit_of_work)

    @property
    def _hit_boxes(self) -> Dict[HitBoxId, HitBoxAggregate]:
        return self._data_store.hit_boxes

    def find_by_id(self, entity_id: HitBoxId) -> Optional[HitBoxAggregate]:
        return self._clone(self._hit_boxes.get(entity_id))

    def find_by_ids(self, entity_ids: List[HitBoxId]) -> List[HitBoxAggregate]:
        return [self._clone(self._hit_boxes[eid]) for eid in entity_ids if eid in self._hit_boxes]

    def save(self, entity: HitBoxAggregate) -> HitBoxAggregate:
        cloned = self._clone(entity)

        def operation():
            self._hit_boxes[cloned.hit_box_id] = cloned
            return cloned

        self._register_aggregate(entity)
        return self._execute_operation(operation)

    def delete(self, entity_id: HitBoxId) -> bool:
        def operation():
            if entity_id in self._hit_boxes:
                del self._hit_boxes[entity_id]
                return True
            return False

        return self._execute_operation(operation)

    def find_all(self) -> List[HitBoxAggregate]:
        return [self._clone(hb) for hb in self._hit_boxes.values()]

    def find_by_spot_id(self, spot_id: SpotId) -> List[HitBoxAggregate]:
        return [self._clone(hb) for hb in self._hit_boxes.values() if hb.spot_id == spot_id]

    def find_active_by_spot_id(self, spot_id: SpotId) -> List[HitBoxAggregate]:
        return [self._clone(hb) for hb in self._hit_boxes.values() if hb.spot_id == spot_id and hb.is_active]

    def generate_id(self) -> HitBoxId:
        def operation():
            hit_box_id = HitBoxId(self._data_store.next_hit_box_id)
            self._data_store.next_hit_box_id += 1
            return hit_box_id

        return self._execute_operation(operation)

    def batch_generate_ids(self, count: int) -> List[HitBoxId]:
        def operation():
            ids = []
            for _ in range(count):
                ids.append(HitBoxId(self._data_store.next_hit_box_id))
                self._data_store.next_hit_box_id += 1
            return ids

        return self._execute_operation(operation)

    def save_all(self, entities: List[HitBoxAggregate]) -> None:
        cloned_entities = [self._clone(e) for e in entities]

        def operation():
            for entity in cloned_entities:
                self._hit_boxes[entity.hit_box_id] = entity

        for entity in entities:
            self._register_aggregate(entity)
        self._execute_operation(operation)
