"""
ItemInfoQueryService専用のアプリケーション例外
"""

from typing import Optional
from src.domain.common.exception import DomainException
from src.application.common.exceptions import ApplicationException


class ItemInfoQueryApplicationException(ApplicationException):
    """ItemInfoQueryアプリケーション層例外"""

    @classmethod
    def from_domain_error(cls, e: DomainException) -> "ItemInfoQueryApplicationException":
        """ドメイン例外からの変換

        Args:
            e: ドメイン例外

        Returns:
            ItemInfoQueryApplicationException: 変換されたアプリケーション例外
        """
        return cls(f"Domain error in ItemInfoQuery usecase: {e.error_code}", cause=e)

    @classmethod
    def item_spec_not_found(cls, item_spec_id: int) -> "ItemInfoQueryApplicationException":
        """アイテムスペックが見つからない場合の例外

        Args:
            item_spec_id: アイテムスペックID

        Returns:
            ItemInfoQueryApplicationException: アプリケーション例外
        """
        return cls(
            f"Item spec not found: {item_spec_id}",
            item_spec_id=item_spec_id
        )

    @classmethod
    def invalid_request(cls, message: str, **context) -> "ItemInfoQueryApplicationException":
        """無効なリクエストの場合の例外

        Args:
            message: エラーメッセージ
            **context: 追加のコンテキスト情報

        Returns:
            ItemInfoQueryApplicationException: アプリケーション例外
        """
        return cls(f"Invalid request: {message}", **context)
