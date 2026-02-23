from typing import Dict, Optional, List
from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import LootTableAggregate
from ai_rpg_world.domain.item.repository.loot_table_repository import LootTableRepository
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId


class InMemoryLootTableRepository(LootTableRepository):
    """メモリ内ドロップテーブルリポジトリ"""

    def __init__(self, initial_data: Optional[Dict[LootTableId, LootTableAggregate]] = None):
        self._data: Dict[LootTableId, LootTableAggregate] = initial_data or {}

    def find_by_id(self, entity_id: LootTableId) -> Optional[LootTableAggregate]:
        return self._data.get(entity_id)

    def find_all(self) -> List[LootTableAggregate]:
        return list(self._data.values())

    def find_by_ids(self, entity_ids: List[LootTableId]) -> List[LootTableAggregate]:
        return [self._data[eid] for eid in entity_ids if eid in self._data]

    def save(self, entity: LootTableAggregate) -> LootTableAggregate:
        self._data[entity.loot_table_id] = entity
        return entity

    def delete(self, entity_id: LootTableId) -> bool:
        if entity_id in self._data:
            del self._data[entity_id]
            return True
        return False
