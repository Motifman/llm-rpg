"""スポーン定義（スポット単位のスポーンテーブル）のインメモリリポジトリ。"""

from typing import Optional

from ai_rpg_world.domain.monster.repository.spawn_table_repository import SpawnTableRepository
from ai_rpg_world.domain.monster.value_object.spot_spawn_table import SpotSpawnTable
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore


class InMemorySpawnTableRepository(SpawnTableRepository):
    """
    スポット単位のスポーンテーブルのインメモリ実装。
    設定的な要素は後から差し替え可能。データストアの spawn_tables を参照する。
    """

    def __init__(self, data_store: Optional[InMemoryDataStore] = None):
        self._data_store = data_store or InMemoryDataStore()

    def find_by_spot_id(self, spot_id: SpotId) -> Optional[SpotSpawnTable]:
        return self._data_store.spawn_tables.get(spot_id)

    def add_table(self, table: SpotSpawnTable) -> None:
        """スポーンテーブルを登録する（テスト・初期データ用）。"""
        self._data_store.spawn_tables[table.spot_id] = table
