from abc import ABC
from typing import List, Optional

from src.domain.common.repository import Repository
from src.domain.item.entity.unique_item import UniqueItem


class UniqueItemRepository(Repository[UniqueItem], ABC):
    """ユニークアイテムのリポジトリインターフェース"""

    @abstractmethod
    def find_by_item_id(self, item_id: int) -> List[UniqueItem]:
        """基本アイテムIDでユニークアイテムを検索"""
        pass

    @abstractmethod
    def find_broken_items(self) -> List[UniqueItem]:
        """破損したアイテムを検索"""
        pass

    @abstractmethod
    def find_tradeable_items(self) -> List[UniqueItem]:
        """取引可能なユニークアイテムを検索"""
        pass

    @abstractmethod
    def find_by_owner_id(self, owner_id: int) -> List[UniqueItem]:
        """所有者IDで検索（将来的な拡張用）"""
        pass
