"""
レシピ情報検索関連の例外定義
"""

from typing import Optional
from ai_rpg_world.application.inventory.exceptions.base_exception import ApplicationException


class RecipeInfoQueryException(ApplicationException):
    """レシピ情報検索関連の例外"""

    def __init__(self, message: str, error_code: str = None, recipe_id: Optional[int] = None, **context):
        # 既存の動作を維持しつつ、新しい基底クラスに適合
        all_context = context.copy()
        if recipe_id is not None:
            all_context['recipe_id'] = recipe_id
        super().__init__(message, error_code, **all_context)


class RecipeNotFoundException(RecipeInfoQueryException):
    """レシピが見つからない場合の例外"""

    def __init__(self, recipe_id: int):
        message = f"レシピが見つかりません: {recipe_id}"
        super().__init__(message, "RECIPE_NOT_FOUND", recipe_id=recipe_id)


class InvalidRecipeIdException(RecipeInfoQueryException):
    """無効なレシピIDの場合の例外"""

    def __init__(self, recipe_id: int):
        message = f"無効なレシピIDです: {recipe_id}"
        super().__init__(message, "INVALID_RECIPE_ID", recipe_id=recipe_id)


class RecipeSearchException(RecipeInfoQueryException):
    """レシピ検索関連の例外"""

    def __init__(self, message: str, search_criteria: str):
        self.search_criteria = search_criteria
        super().__init__(message, "RECIPE_SEARCH_ERROR")
