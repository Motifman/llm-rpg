"""
InMemoryRecipeRepository - RecipeAggregateを使用するインメモリ実装
"""
from typing import List, Optional, Dict
from ai_rpg_world.domain.item.repository.recipe_repository import RecipeRepository
from ai_rpg_world.domain.item.aggregate.recipe_aggregate import RecipeAggregate
from ai_rpg_world.domain.item.value_object.recipe_id import RecipeId
from ai_rpg_world.domain.item.value_object.recipe_ingredient import RecipeIngredient
from ai_rpg_world.domain.item.value_object.recipe_result import RecipeResult
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId


class InMemoryRecipeRepository(RecipeRepository):
    """RecipeAggregateを使用するインメモリリポジトリ"""

    def __init__(self):
        self._recipes: Dict[RecipeId, RecipeAggregate] = {}
        self._result_item_to_recipes: Dict[ItemSpecId, List[RecipeAggregate]] = {}
        self._ingredient_item_to_recipes: Dict[ItemSpecId, List[RecipeAggregate]] = {}
        self._next_recipe_id = RecipeId(1)

        # サンプルレシピデータをセットアップ
        self._setup_sample_data()

    def _setup_sample_data(self):
        """サンプルレシピデータのセットアップ"""
        # レシピ1: 鉄の剣の作成
        iron_sword_recipe = RecipeAggregate(
            recipe_id=RecipeId(1),
            name="鉄の剣の作成",
            description="鉄鉱石と鋼鉄インゴットから鉄の剣を作成します。",
            ingredients=[
                RecipeIngredient(item_spec_id=ItemSpecId(4), quantity=2),  # 鉄鉱石 x2
                RecipeIngredient(item_spec_id=ItemSpecId(5), quantity=1),  # 鋼鉄インゴット x1
            ],
            result=RecipeResult(item_spec_id=ItemSpecId(1), quantity=1)  # 鉄の剣 x1
        )
        self._save_recipe(iron_sword_recipe)

        # レシピ2: 回復ポーションの作成
        healing_potion_recipe = RecipeAggregate(
            recipe_id=RecipeId(2),
            name="回復ポーションの作成",
            description="ハーブと水から回復ポーションを作成します。",
            ingredients=[
                RecipeIngredient(item_spec_id=ItemSpecId(6), quantity=1),  # ハーブ x1
                RecipeIngredient(item_spec_id=ItemSpecId(7), quantity=1),  # 水 x1
            ],
            result=RecipeResult(item_spec_id=ItemSpecId(8), quantity=1)  # 回復ポーション x1
        )
        self._save_recipe(healing_potion_recipe)

        # レシピ3: 鋼鉄インゴットの作成
        steel_ingot_recipe = RecipeAggregate(
            recipe_id=RecipeId(3),
            name="鋼鉄インゴットの作成",
            description="鉄鉱石と石炭から鋼鉄インゴットを作成します。",
            ingredients=[
                RecipeIngredient(item_spec_id=ItemSpecId(4), quantity=1),  # 鉄鉱石 x1
                RecipeIngredient(item_spec_id=ItemSpecId(9), quantity=1),  # 石炭 x1
            ],
            result=RecipeResult(item_spec_id=ItemSpecId(5), quantity=1)  # 鋼鉄インゴット x1
        )
        self._save_recipe(steel_ingot_recipe)

    def _save_recipe(self, recipe: RecipeAggregate):
        """レシピを保存し、インデックスを更新"""
        self._recipes[recipe.recipe_id] = recipe

        # 結果アイテム別のインデックスを更新
        result_item_id = recipe.result.item_spec_id
        if result_item_id not in self._result_item_to_recipes:
            self._result_item_to_recipes[result_item_id] = []
        self._result_item_to_recipes[result_item_id].append(recipe)

        # 材料アイテム別のインデックスを更新
        for ingredient in recipe.ingredients:
            ingredient_item_id = ingredient.item_spec_id
            if ingredient_item_id not in self._ingredient_item_to_recipes:
                self._ingredient_item_to_recipes[ingredient_item_id] = []
            self._ingredient_item_to_recipes[ingredient_item_id].append(recipe)

    def find_by_id(self, recipe_id: RecipeId) -> Optional[RecipeAggregate]:
        """IDでレシピを検索"""
        return self._recipes.get(recipe_id)

    def find_by_ids(self, recipe_ids: List[RecipeId]) -> List[RecipeAggregate]:
        """IDのリストでレシピを検索"""
        return [recipe for recipe_id, recipe in self._recipes.items() if recipe_id in recipe_ids]

    def find_all(self) -> List[RecipeAggregate]:
        """全レシピを取得"""
        return list(self._recipes.values())

    def find_by_result_item(self, item_spec_id: ItemSpecId) -> List[RecipeAggregate]:
        """指定アイテムを作成できるレシピを取得"""
        return self._result_item_to_recipes.get(item_spec_id, [])

    def find_by_ingredient(self, item_spec_id: ItemSpecId) -> List[RecipeAggregate]:
        """指定アイテムを材料として使用するレシピを取得"""
        return self._ingredient_item_to_recipes.get(item_spec_id, [])

    def save(self, recipe: RecipeAggregate) -> RecipeAggregate:
        """レシピを保存"""
        self._save_recipe(recipe)
        return recipe

    def delete(self, recipe_id: RecipeId) -> bool:
        """レシピを削除"""
        if recipe_id in self._recipes:
            recipe = self._recipes[recipe_id]

            # インデックスからも削除
            result_item_id = recipe.result.item_spec_id
            if result_item_id in self._result_item_to_recipes:
                self._result_item_to_recipes[result_item_id] = [
                    r for r in self._result_item_to_recipes[result_item_id] if r.recipe_id != recipe_id
                ]

            for ingredient in recipe.ingredients:
                ingredient_item_id = ingredient.item_spec_id
                if ingredient_item_id in self._ingredient_item_to_recipes:
                    self._ingredient_item_to_recipes[ingredient_item_id] = [
                        r for r in self._ingredient_item_to_recipes[ingredient_item_id] if r.recipe_id != recipe_id
                    ]

            del self._recipes[recipe_id]
            return True
        return False
