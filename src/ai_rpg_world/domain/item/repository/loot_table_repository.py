from abc import ABC, abstractmethod
from typing import Optional, List
from ai_rpg_world.domain.common.repository import ReadRepository
from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import LootTableAggregate
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId


class LootTableRepository(ReadRepository[LootTableAggregate, LootTableId], ABC):
    """ドロップテーブルのリポジトリインターフェース"""
    pass


class LootTableWriter(ABC):
    """ドロップテーブルの投入専用 writer ポート"""

    @abstractmethod
    def replace_table(self, table: LootTableAggregate) -> None:
        """テーブルを丸ごと置き換える。"""
        pass

    @abstractmethod
    def delete_table(self, loot_table_id: LootTableId) -> bool:
        """テーブルを削除する。"""
        pass
