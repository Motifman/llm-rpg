"""
GlobalMarketQueryService専用のアプリケーション例外
"""

from typing import Optional
from src.domain.common.exception import DomainException
from src.application.common.exceptions import ApplicationException


class GlobalMarketQueryApplicationException(ApplicationException):
    """GlobalMarketQueryアプリケーション層例外"""

    @classmethod
    def from_domain_error(cls, e: DomainException) -> "GlobalMarketQueryApplicationException":
        """ドメイン例外からの変換

        Args:
            e: ドメイン例外

        Returns:
            GlobalMarketQueryApplicationException: 変換されたアプリケーション例外
        """
        return cls(f"Domain error in GlobalMarketQuery usecase: {e.error_code}", cause=e)

    @classmethod
    def invalid_filter(cls, message: str, **context) -> "GlobalMarketQueryApplicationException":
        """無効なフィルタ条件の場合の例外

        Args:
            message: エラーメッセージ
            **context: 追加のコンテキスト情報

        Returns:
            GlobalMarketQueryApplicationException: アプリケーション例外
        """
        return cls(f"Invalid filter: {message}", **context)

    @classmethod
    def listings_not_found(cls, filter_description: str) -> "GlobalMarketQueryApplicationException":
        """出品が見つからない場合の例外

        Args:
            filter_description: フィルタ条件の説明

        Returns:
            GlobalMarketQueryApplicationException: アプリケーション例外
        """
        return cls(
            f"No listings found for filter: {filter_description}",
            filter_description=filter_description
        )
