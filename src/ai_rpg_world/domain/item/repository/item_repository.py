from abc import ABC, abstractmethod
from typing import List, Optional

from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity


class ItemSpecRepository(Repository[ItemSpec], ABC):
    """アイテム仕様のリポジトリインターフェース"""

    @abstractmethod
    def find_by_id(self, item_spec_id: ItemSpecId) -> Optional[ItemSpec]:
        """アイテム仕様IDで検索"""
        pass

    @abstractmethod
    def find_by_type(self, item_type: ItemType) -> List[ItemSpec]:
        """アイテムタイプで検索"""
        pass

    @abstractmethod
    def find_by_rarity(self, rarity: Rarity) -> List[ItemSpec]:
        """レアリティで検索"""
        pass

    @abstractmethod
    def find_tradeable_items(self) -> List[ItemSpec]:
        """取引可能なアイテムを検索"""
        pass

    @abstractmethod
    def find_by_name(self, name: str) -> Optional[ItemSpec]:
        """名前で検索"""
        pass
