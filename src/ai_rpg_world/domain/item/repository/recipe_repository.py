from abc import ABC, abstractmethod
from typing import List, Optional
from ai_rpg_world.domain.common.repository import ReadRepository
from ai_rpg_world.domain.item.value_object.recipe_id import RecipeId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.aggregate.recipe_aggregate import RecipeAggregate


class RecipeRepository(ReadRepository[RecipeAggregate, RecipeId], ABC):
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


class RecipeWriter(ABC):
    """レシピの投入専用 writer ポート"""

    @abstractmethod
    def replace_recipe(self, recipe: RecipeAggregate) -> None:
        """レシピを丸ごと置き換える。"""
        pass

    @abstractmethod
    def delete_recipe(self, recipe_id: RecipeId) -> bool:
        """レシピを削除する。"""
        pass
