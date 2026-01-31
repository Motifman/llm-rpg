from abc import ABC, abstractmethod
from typing import List, Optional

from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.item.read_model.item_spec_read_model import ItemSpecReadModel
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity


class ItemSpecRepository(Repository[ItemSpecReadModel, ItemSpecId], ABC):
    """アイテム仕様のリポジトリインターフェース"""
    @abstractmethod
    def find_by_type(self, item_type: ItemType) -> List[ItemSpecReadModel]:
        """アイテムタイプで検索"""
        pass

    @abstractmethod
    def find_by_rarity(self, rarity: Rarity) -> List[ItemSpecReadModel]:
        """レアリティで検索"""
        pass

    @abstractmethod
    def find_tradeable_items(self) -> List[ItemSpecReadModel]:
        """取引可能なアイテムを検索"""
        pass

    @abstractmethod
    def find_by_name(self, name: str) -> Optional[ItemSpecReadModel]:
        """名前で検索"""
        pass
