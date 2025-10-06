"""
RecipeInfoQueryService専用のアプリケーション例外
"""

from typing import Optional
from src.domain.common.exception import DomainException
from src.application.common.exceptions import ApplicationException


class RecipeInfoQueryApplicationException(ApplicationException):
    """RecipeInfoQueryアプリケーション層例外"""

    @classmethod
    def from_domain_error(cls, e: DomainException) -> "RecipeInfoQueryApplicationException":
        """ドメイン例外からの変換

        Args:
            e: ドメイン例外

        Returns:
            RecipeInfoQueryApplicationException: 変換されたアプリケーション例外
        """
        return cls(f"Domain error in RecipeInfoQuery usecase: {e.error_code}", cause=e)

    @classmethod
    def recipe_not_found(cls, recipe_id: int) -> "RecipeInfoQueryApplicationException":
        """レシピが見つからない場合の例外

        Args:
            recipe_id: レシピID

        Returns:
            RecipeInfoQueryApplicationException: アプリケーション例外
        """
        return cls(
            f"Recipe not found: {recipe_id}",
            recipe_id=recipe_id
        )

    @classmethod
    def invalid_recipe_id(cls, recipe_id: int) -> "RecipeInfoQueryApplicationException":
        """無効なレシピIDの場合の例外

        Args:
            recipe_id: レシピID

        Returns:
            RecipeInfoQueryApplicationException: アプリケーション例外
        """
        return cls(
            f"Invalid recipe ID: {recipe_id}",
            recipe_id=recipe_id
        )

    @classmethod
    def invalid_request(cls, message: str, **context) -> "RecipeInfoQueryApplicationException":
        """無効なリクエストの場合の例外

        Args:
            message: エラーメッセージ
            **context: 追加のコンテキスト情報

        Returns:
            RecipeInfoQueryApplicationException: アプリケーション例外
        """
        return cls(f"Invalid request: {message}", **context)
