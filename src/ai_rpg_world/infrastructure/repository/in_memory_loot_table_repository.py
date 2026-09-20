
from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import LootTableAggregate
from ai_rpg_world.domain.item.repository.loot_table_repository import (
    LootTableRepository,
    LootTableWriter,
)
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId


class InMemoryLootTableRepository(LootTableRepository, LootTableWriter):
    """メモリ内ドロップテーブルリポジトリ"""

    def __init__(self, initial_data: dict[LootTableId, LootTableAggregate] | None = None):
        self._data: dict[LootTableId, LootTableAggregate] = initial_data or {}

    def find_by_id(self, entity_id: LootTableId) -> LootTableAggregate | None:
        return self._data.get(entity_id)

    def find_all(self) -> list[LootTableAggregate]:
        return list(self._data.values())

    def find_by_ids(self, entity_ids: list[LootTableId]) -> list[LootTableAggregate]:
        return [self._data[eid] for eid in entity_ids if eid in self._data]

    def save(self, entity: LootTableAggregate) -> LootTableAggregate:
        self._data[entity.loot_table_id] = entity
        return entity

    def delete(self, entity_id: LootTableId) -> bool:
        if entity_id in self._data:
            del self._data[entity_id]
            return True
        return False

    def replace_table(self, table: LootTableAggregate) -> None:
        self.save(table)

    def delete_table(self, loot_table_id: LootTableId) -> bool:
        return self.delete(loot_table_id)
