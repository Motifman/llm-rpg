from abc import ABC, abstractmethod
from typing import Optional
from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import LootTableAggregate


class LootTableRepository(Repository[LootTableAggregate, str], ABC):
    """ドロップテーブルのリポジトリインターフェース"""
    pass
