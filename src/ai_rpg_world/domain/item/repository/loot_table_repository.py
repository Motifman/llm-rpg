from abc import ABC, abstractmethod
from typing import Optional, List
from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import LootTableAggregate
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId


class LootTableRepository(Repository[LootTableAggregate, LootTableId], ABC):
    """ドロップテーブルのリポジトリインターフェース"""
    pass
