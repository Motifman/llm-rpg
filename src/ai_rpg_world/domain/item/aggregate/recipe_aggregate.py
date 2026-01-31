from typing import List, Dict
from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.item.value_object.recipe_id import RecipeId
from ai_rpg_world.domain.item.value_object.recipe_ingredient import RecipeIngredient
from ai_rpg_world.domain.item.value_object.recipe_result import RecipeResult
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.aggregate.item_aggregate import ItemAggregate
from ai_rpg_world.domain.item.exception.item_exception import InvalidRecipeException


class RecipeAggregate(AggregateRoot):
    """レシピ集約

    レシピの情報を管理し、合成ロジックを提供する。
    """

    def __init__(
        self,
        recipe_id: RecipeId,
        name: str,
        description: str,
        ingredients: List[RecipeIngredient],
        result: RecipeResult
    ):
        super().__init__()
        self._recipe_id = recipe_id
        self._name = name
        self._description = description
        self._ingredients = ingredients  # 値オブジェクトのリスト
        self._result = result  # 値オブジェクト

        self._validate()

    def _validate(self) -> None:
        """レシピの妥当性検証"""
        if not self._name.strip():
            raise InvalidRecipeException(f"Recipe {self._recipe_id.value}: name must not be empty")
        if not self._description.strip():
            raise InvalidRecipeException(f"Recipe {self._recipe_id.value}: description must not be empty")
        if not self._ingredients:
            raise InvalidRecipeException(f"Recipe {self._recipe_id.value}: ingredients must not be empty")
        if len(self._ingredients) != len(set(ing.item_spec_id for ing in self._ingredients)):
            raise InvalidRecipeException(f"Recipe {self._recipe_id.value}: ingredients must have unique item_spec_ids")

    @property
    def recipe_id(self) -> RecipeId:
        """レシピID"""
        return self._recipe_id

    @property
    def name(self) -> str:
        """レシピ名"""
        return self._name

    @property
    def description(self) -> str:
        """レシピ説明"""
        return self._description

    @property
    def ingredients(self) -> List[RecipeIngredient]:
        """材料リスト"""
        return self._ingredients.copy()

    @property
    def result(self) -> RecipeResult:
        """結果"""
        return self._result

    def can_craft_with(self, available_items: Dict[ItemSpecId, int]) -> bool:
        """所持アイテムで合成可能かチェック

        Args:
            available_items: {ItemSpecId: quantity} の辞書

        Returns:
            bool: 合成可能かどうか
        """
        for ingredient in self._ingredients:
            available_quantity = available_items.get(ingredient.item_spec_id, 0)
            if available_quantity < ingredient.quantity:
                return False
        return True

    def get_missing_ingredients(self, available_items: Dict[ItemSpecId, int]) -> List[RecipeIngredient]:
        """不足している材料を取得

        Args:
            available_items: {ItemSpecId: quantity} の辞書

        Returns:
            List[RecipeIngredient]: 不足している材料のリスト
        """
        missing = []
        for ingredient in self._ingredients:
            available_quantity = available_items.get(ingredient.item_spec_id, 0)
            if available_quantity < ingredient.quantity:
                missing.append(RecipeIngredient(
                    item_spec_id=ingredient.item_spec_id,
                    quantity=ingredient.quantity - available_quantity
                ))
        return missing

    @staticmethod
    def calculate_available_quantities(inventory: List[ItemAggregate]) -> Dict[ItemSpecId, int]:
        """インベントリから利用可能なアイテム数を計算（静的メソッド）"""
        available = {}
        for item in inventory:
            spec_id = item.item_spec.item_spec_id
            available[spec_id] = available.get(spec_id, 0) + item.quantity
        return available

    def __eq__(self, other: object) -> bool:
        """等価性比較"""
        if not isinstance(other, RecipeAggregate):
            return False
        return self._recipe_id == other._recipe_id

    def __hash__(self) -> int:
        """ハッシュ値"""
        return hash(self._recipe_id)

    def __str__(self) -> str:
        """文字列表現"""
        ingredients_str = ", ".join(str(ing) for ing in self._ingredients)
        return f"RecipeAggregate({self._name}: {ingredients_str} -> {self._result})"
