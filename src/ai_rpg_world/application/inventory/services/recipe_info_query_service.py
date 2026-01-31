from typing import List, Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from ai_rpg_world.domain.item.repository.recipe_repository import RecipeRepository
from ai_rpg_world.domain.item.value_object.recipe_id import RecipeId
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.application.inventory.contracts.dtos import RecipeDto, RecipeIngredientDto, RecipeResultDto
from ai_rpg_world.application.inventory.exceptions.recipe_info_query_application_exception import RecipeInfoQueryApplicationException
from ai_rpg_world.application.common.exceptions import SystemErrorException


class RecipeInfoQueryService:
    """レシピ情報検索サービス"""

    def __init__(self, recipe_repository: "RecipeRepository"):
        self._recipe_repository = recipe_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(self, operation, context: dict):
        """共通の例外処理を実行"""
        try:
            return operation()
        except RecipeInfoQueryApplicationException as e:
            # アプリケーション例外はそのまま再スロー
            raise e
        except DomainException as e:
            # ドメイン例外をアプリケーション例外に変換
            raise RecipeInfoQueryApplicationException.from_domain_error(e)
        except Exception as e:
            # 不明な例外はシステムエラーとしてログ出力し、SystemErrorExceptionをスロー
            self._logger.error(f"Unexpected error in {context.get('action', 'unknown')}: {str(e)}",
                             extra={'error_details': context})
            raise SystemErrorException(f"{context.get('action', 'unknown')} failed: {str(e)}",
                                     original_exception=e)

    def get_recipe(self, recipe_id: int) -> RecipeDto:
        """レシピを取得"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_recipe_impl(recipe_id),
            context={
                "action": "get_recipe",
                "recipe_id": recipe_id
            }
        )

    def _get_recipe_impl(self, recipe_id: int) -> RecipeDto:
        """レシピ取得の実装"""
        recipe = self._recipe_repository.find_by_id(RecipeId(recipe_id))
        if recipe is None:
            raise RecipeInfoQueryApplicationException.recipe_not_found(recipe_id)

        return RecipeDto(
            recipe_id=recipe.recipe_id.value,
            name=recipe.name,
            description=recipe.description,
            ingredients=[
                RecipeIngredientDto(
                    item_spec_id=ing.item_spec_id.value,
                    quantity=ing.quantity
                )
                for ing in recipe.ingredients
            ],
            result=RecipeResultDto(
                item_spec_id=recipe.result.item_spec_id.value,
                quantity=recipe.result.quantity
            )
        )

    def find_recipes_by_result_item(self, item_spec_id: int) -> List[RecipeDto]:
        """指定アイテムを作成できるレシピを取得"""
        return self._execute_with_error_handling(
            operation=lambda: self._find_recipes_by_result_item_impl(item_spec_id),
            context={
                "action": "find_recipes_by_result_item",
                "item_spec_id": item_spec_id
            }
        )

    def _find_recipes_by_result_item_impl(self, item_spec_id: int) -> List[RecipeDto]:
        """指定アイテムを作成できるレシピ取得の実装"""
        recipes = self._recipe_repository.find_by_result_item(ItemSpecId(item_spec_id))
        return [
            RecipeDto(
                recipe_id=recipe.recipe_id.value,
                name=recipe.name,
                description=recipe.description,
                ingredients=[
                    RecipeIngredientDto(
                        item_spec_id=ing.item_spec_id.value,
                        quantity=ing.quantity
                    )
                    for ing in recipe.ingredients
                ],
                result=RecipeResultDto(
                    item_spec_id=recipe.result.item_spec_id.value,
                    quantity=recipe.result.quantity
                )
            )
            for recipe in recipes
        ]

    def find_recipes_by_ingredient(self, item_spec_id: int) -> List[RecipeDto]:
        """指定アイテムを材料として使用するレシピを取得"""
        return self._execute_with_error_handling(
            operation=lambda: self._find_recipes_by_ingredient_impl(item_spec_id),
            context={
                "action": "find_recipes_by_ingredient",
                "item_spec_id": item_spec_id
            }
        )

    def _find_recipes_by_ingredient_impl(self, item_spec_id: int) -> List[RecipeDto]:
        """指定アイテムを材料として使用するレシピ取得の実装"""
        recipes = self._recipe_repository.find_by_ingredient(ItemSpecId(item_spec_id))
        return [
            RecipeDto(
                recipe_id=recipe.recipe_id.value,
                name=recipe.name,
                description=recipe.description,
                ingredients=[
                    RecipeIngredientDto(
                        item_spec_id=ing.item_spec_id.value,
                        quantity=ing.quantity
                    )
                    for ing in recipe.ingredients
                ],
                result=RecipeResultDto(
                    item_spec_id=recipe.result.item_spec_id.value,
                    quantity=recipe.result.quantity
                )
            )
            for recipe in recipes
        ]

    def get_all_recipes(self) -> List[RecipeDto]:
        """全レシピを取得"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_all_recipes_impl(),
            context={
                "action": "get_all_recipes"
            }
        )

    def _get_all_recipes_impl(self) -> List[RecipeDto]:
        """全レシピ取得の実装"""
        recipes = self._recipe_repository.find_all()
        return [
            RecipeDto(
                recipe_id=recipe.recipe_id.value,
                name=recipe.name,
                description=recipe.description,
                ingredients=[
                    RecipeIngredientDto(
                        item_spec_id=ing.item_spec_id.value,
                        quantity=ing.quantity
                    )
                    for ing in recipe.ingredients
                ],
                result=RecipeResultDto(
                    item_spec_id=recipe.result.item_spec_id.value,
                    quantity=recipe.result.quantity
                )
            )
            for recipe in recipes
        ]
