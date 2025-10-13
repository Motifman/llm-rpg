"""
MarketOverviewQueryService専用のアプリケーション例外
"""

from typing import Optional
from src.domain.common.exception import DomainException
from src.application.common.exceptions import ApplicationException


class MarketOverviewQueryApplicationException(ApplicationException):
    """MarketOverviewQueryアプリケーション層例外"""

    @classmethod
    def from_domain_error(cls, e: DomainException) -> "MarketOverviewQueryApplicationException":
        """ドメイン例外からの変換

        Args:
            e: ドメイン例外

        Returns:
            MarketOverviewQueryApplicationException: 変換されたアプリケーション例外
        """
        return cls(f"Domain error in MarketOverviewQuery usecase: {e.error_code}", cause=e)

    @classmethod
    def market_overview_not_found(cls) -> "MarketOverviewQueryApplicationException":
        """市場概要が見つからない場合の例外

        Returns:
            MarketOverviewQueryApplicationException: アプリケーション例外
        """
        return cls("Market overview information not found")

    @classmethod
    def invalid_request(cls, message: str, **context) -> "MarketOverviewQueryApplicationException":
        """無効なリクエストの場合の例外

        Args:
            message: エラーメッセージ
            **context: 追加のコンテキスト情報

        Returns:
            MarketOverviewQueryApplicationException: アプリケーション例外
        """
        return cls(f"Invalid request: {message}", **context)
