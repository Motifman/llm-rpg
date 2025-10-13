"""
TradeMarketQueryService専用のアプリケーション例外
"""

from typing import Optional
from src.domain.common.exception import DomainException
from src.application.common.exceptions import ApplicationException


class TradeMarketQueryApplicationException(ApplicationException):
    """TradeMarketQueryアプリケーション層例外"""

    @classmethod
    def from_domain_error(cls, e: DomainException) -> "TradeMarketQueryApplicationException":
        """ドメイン例外からの変換

        Args:
            e: ドメイン例外

        Returns:
            TradeMarketQueryApplicationException: 変換されたアプリケーション例外
        """
        return cls(f"Domain error in TradeMarketQuery usecase: {e.error_code}", cause=e)

    @classmethod
    def item_not_found(cls, item_name: str) -> "TradeMarketQueryApplicationException":
        """アイテムが見つからない場合の例外

        Args:
            item_name: アイテム名

        Returns:
            TradeMarketQueryApplicationException: アプリケーション例外
        """
        return cls(
            f"Item market information not found: {item_name}",
            item_name=item_name
        )

    @classmethod
    def invalid_request(cls, message: str, **context) -> "TradeMarketQueryApplicationException":
        """無効なリクエストの場合の例外

        Args:
            message: エラーメッセージ
            **context: 追加のコンテキスト情報

        Returns:
            TradeMarketQueryApplicationException: アプリケーション例外
        """
        return cls(f"Invalid request: {message}", **context)

    @classmethod
    def invalid_limit(cls, limit: int) -> "TradeMarketQueryApplicationException":
        """無効なlimit値の場合の例外

        Args:
            limit: 無効なlimit値

        Returns:
            TradeMarketQueryApplicationException: アプリケーション例外
        """
        return cls(
            f"Limit must be non-negative, got {limit}",
            limit=limit
        )
