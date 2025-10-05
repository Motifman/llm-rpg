from abc import ABC, abstractmethod
from typing import List, Optional
from src.domain.common.repository import Repository
from src.domain.item.value_object.recipe_id import RecipeId
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.aggregate.recipe_aggregate import RecipeAggregate


class RecipeRepository(Repository[RecipeAggregate, RecipeId], ABC):
    """レシピリポジトリインターフェース"""

    # Recipe特有のメソッド
    @abstractmethod
    def find_by_result_item(self, item_spec_id: ItemSpecId) -> List[RecipeAggregate]:
        """指定アイテムを作成できるレシピを取得

        Args:
            item_spec_id: 結果アイテムのスペックID

        Returns:
            List[RecipeAggregate]: 指定アイテムを作成できるレシピのリスト
        """
        pass

    @abstractmethod
    def find_by_ingredient(self, item_spec_id: ItemSpecId) -> List[RecipeAggregate]:
        """指定アイテムを材料として使用するレシピを取得

        Args:
            item_spec_id: 材料アイテムのスペックID

        Returns:
            List[RecipeAggregate]: 指定アイテムを材料として使用するレシピのリスト
        """
        pass