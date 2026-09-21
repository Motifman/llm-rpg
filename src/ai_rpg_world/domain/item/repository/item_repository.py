from abc import ABC, abstractmethod

from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId


class ItemRepository(Repository[ItemAggregate, ItemInstanceId], ABC):
    """アイテム集約のリポジトリインターフェース"""

    @abstractmethod
    def generate_item_instance_id(self) -> ItemInstanceId:
        """新しいItemInstanceIdを生成"""
        pass

    @abstractmethod
    def find_by_id(self, item_instance_id: ItemInstanceId) -> ItemAggregate | None:
        """アイテム集約をIDで検索"""
        pass

    @abstractmethod
    def find_by_spec_id(self, item_spec_id: ItemSpecId) -> list[ItemAggregate]:
        """アイテム仕様IDで検索"""
        pass

    @abstractmethod
    def find_by_type(self, item_type: ItemType) -> list[ItemAggregate]:
        """アイテムタイプで検索"""
        pass

    @abstractmethod
    def find_by_rarity(self, rarity: Rarity) -> list[ItemAggregate]:
        """レアリティで検索"""
        pass

    @abstractmethod
    def find_broken_items(self) -> list[ItemAggregate]:
        """破損したアイテムを検索"""
        pass

    @abstractmethod
    def find_tradeable_items(self) -> list[ItemAggregate]:
        """取引可能なアイテムを検索"""
        pass

    @abstractmethod
    def find_by_owner_id(self, owner_id: int) -> list[ItemAggregate]:
        """所有者IDで検索（将来的な拡張用）"""
        pass
