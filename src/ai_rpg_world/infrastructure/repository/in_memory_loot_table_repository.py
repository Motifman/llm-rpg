from typing import Dict, Optional, List
from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import LootTableAggregate
from ai_rpg_world.domain.item.repository.loot_table_repository import LootTableRepository


class InMemoryLootTableRepository(LootTableRepository):
    """メモリ内ドロップテーブルリポジトリ"""
    
    def __init__(self, initial_data: Optional[Dict[str, LootTableAggregate]] = None):
        self._data: Dict[str, LootTableAggregate] = initial_data or {}

    def find_by_id(self, id: str) -> Optional[LootTableAggregate]:
        return self._data.get(id)

    def find_all(self) -> List[LootTableAggregate]:
        return list(self._data.values())

    def find_by_ids(self, ids: List[str]) -> List[LootTableAggregate]:
        return [self._data[id] for id in ids if id in self._data]

    def save(self, aggregate: LootTableAggregate) -> LootTableAggregate:
        self._data[aggregate.loot_table_id] = aggregate
        return aggregate

    def delete(self, id: str) -> None:
        if id in self._data:
            del self._data[id]
