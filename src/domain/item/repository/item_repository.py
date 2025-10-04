from abc import ABC
from typing import List, Optional

from src.domain.common.repository import Repository
from src.domain.item.entity.item import Item
from src.domain.item.enum.item_enum import ItemType, Rarity


class ItemRepository(Repository[Item], ABC):
    """アイテム基本情報のリポジトリインターフェース"""

    @abstractmethod
    def find_by_type(self, item_type: ItemType) -> List[Item]:
        """アイテムタイプで検索"""
        pass

    @abstractmethod
    def find_by_rarity(self, rarity: Rarity) -> List[Item]:
        """レアリティで検索"""
        pass

    @abstractmethod
    def find_tradeable_items(self) -> List[Item]:
        """取引可能なアイテムを検索"""
        pass

    @abstractmethod
    def find_by_name(self, name: str) -> Optional[Item]:
        """名前で検索"""
        pass
