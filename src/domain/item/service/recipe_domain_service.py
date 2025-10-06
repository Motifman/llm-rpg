from typing import List, Dict
from src.domain.item.value_object.item_spec_id import ItemSpecId
from src.domain.item.value_object.recipe_id import RecipeId
from src.domain.item.aggregate.recipe_aggregate import RecipeAggregate
from src.domain.item.aggregate.item_aggregate import ItemAggregate


class RecipeDomainService:
    """レシピドメインサービス"""

    @staticmethod
    def find_recipes_by_result_item(
        item_spec_id: ItemSpecId,
        recipes: List[RecipeAggregate]
    ) -> List[RecipeAggregate]:
        """指定アイテムを作成できるレシピを取得

        Args:
            item_spec_id: 結果アイテムのスペックID
            recipes: 検索対象のレシピリスト

        Returns:
            List[Recipe]: 指定アイテムを作成できるレシピのリスト
        """
        return [
            recipe for recipe in recipes
            if recipe.result.item_spec_id == item_spec_id
        ]

    @staticmethod
    def find_recipes_by_ingredient(
        item_spec_id: ItemSpecId,
        recipes: List[RecipeAggregate]
    ) -> List[RecipeAggregate]:
        """指定アイテムを材料として使用するレシピを取得

        Args:
            item_spec_id: 材料アイテムのスペックID
            recipes: 検索対象のレシピリスト

        Returns:
            List[Recipe]: 指定アイテムを材料として使用するレシピのリスト
        """
        return [
            recipe for recipe in recipes
            if any(ing.item_spec_id == item_spec_id for ing in recipe.ingredients)
        ]


    @staticmethod
    def can_player_craft_recipe(
        recipe: RecipeAggregate,
        player_inventory: List[ItemAggregate]
    ) -> bool:
        """プレイヤーが指定レシピで合成可能かチェック

        Args:
            recipe: チェック対象のレシピ
            player_inventory: プレイヤーのインベントリ

        Returns:
            bool: 合成可能かどうか
        """
        # インベントリから利用可能なアイテム数を集計
        available_items = RecipeAggregate.calculate_available_quantities(player_inventory)

        return recipe.can_craft_with(available_items)

    @staticmethod
    def get_available_recipes_for_player(
        recipes: List[RecipeAggregate],
        player_inventory: List[ItemAggregate]
    ) -> List[RecipeAggregate]:
        """プレイヤーが合成可能なレシピを取得

        Args:
            recipes: 候補レシピリスト
            player_inventory: プレイヤーのインベントリ

        Returns:
            List[Recipe]: 合成可能なレシピのリスト
        """
        available_recipes = []
        inventory_quantities = RecipeAggregate.calculate_available_quantities(player_inventory)

        for recipe in recipes:
            if recipe.can_craft_with(inventory_quantities):
                available_recipes.append(recipe)

        return available_recipes




