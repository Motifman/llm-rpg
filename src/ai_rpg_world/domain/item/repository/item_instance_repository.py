from abc import ABC, abstractmethod
from typing import List, Optional

from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.item.entity.item_instance import ItemInstance
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity


class ItemInstanceRepository(Repository[ItemInstance, ItemInstanceId], ABC):
    """アイテムインスタンスのリポジトリインターフェース"""

    @abstractmethod
    def generate_item_instance_id(self) -> ItemInstanceId:
        """新しいItemInstanceIdを生成"""
        pass

    @abstractmethod
    def find_by_id(self, item_instance_id: ItemInstanceId) -> Optional[ItemInstance]:
        """アイテムインスタンスIDで検索"""
        pass

    @abstractmethod
    def find_by_spec_id(self, item_spec_id: ItemSpecId) -> List[ItemInstance]:
        """アイテム仕様IDで検索"""
        pass

    @abstractmethod
    def find_by_type(self, item_type: ItemType) -> List[ItemInstance]:
        """アイテムタイプで検索"""
        pass

    @abstractmethod
    def find_by_rarity(self, rarity: Rarity) -> List[ItemInstance]:
        """レアリティで検索"""
        pass

    @abstractmethod
    def find_broken_items(self) -> List[ItemInstance]:
        """破損したアイテムを検索"""
        pass

    @abstractmethod
    def find_tradeable_items(self) -> List[ItemInstance]:
        """取引可能なアイテムを検索"""
        pass

    @abstractmethod
    def find_by_owner_id(self, owner_id: int) -> List[ItemInstance]:
        """所有者IDで検索（将来的な拡張用）"""
        pass
