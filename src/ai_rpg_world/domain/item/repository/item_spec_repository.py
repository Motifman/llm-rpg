from abc import ABC, abstractmethod
from typing import List, Optional

from ai_rpg_world.domain.common.repository import ReadRepository
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity


class ItemSpecRepository(ReadRepository[ItemSpec, ItemSpecId], ABC):
    """アイテム仕様のリポジトリインターフェース"""

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


class ItemSpecWriter(ABC):
    """アイテム仕様の投入専用 writer ポート"""

    @abstractmethod
    def replace_spec(self, item_spec: ItemSpec) -> None:
        """アイテム仕様を丸ごと置き換える。"""
        pass

    @abstractmethod
    def delete_spec(self, item_spec_id: ItemSpecId) -> bool:
        """アイテム仕様を削除する。"""
        pass
