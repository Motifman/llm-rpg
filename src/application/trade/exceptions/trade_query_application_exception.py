"""
TradeQueryService専用のアプリケーション例外
"""

from typing import Optional
from src.domain.common.exception import DomainException
from src.application.common.exceptions import ApplicationException


class TradeQueryApplicationException(ApplicationException):
    """TradeQueryアプリケーション層例外"""

    @classmethod
    def from_domain_error(cls, e: DomainException) -> "TradeQueryApplicationException":
        """ドメイン例外からの変換

        Args:
            e: ドメイン例外

        Returns:
            TradeQueryApplicationException: 変換されたアプリケーション例外
        """
        return cls(f"Domain error in TradeQuery usecase: {e.error_code}", cause=e)

    @classmethod
    def trade_not_found(cls, trade_id: str) -> "TradeQueryApplicationException":
        """取引が見つからない場合の例外

        Args:
            trade_id: 取引ID

        Returns:
            TradeQueryApplicationException: アプリケーション例外
        """
        return cls(
            f"Trade not found: {trade_id}",
            trade_id=trade_id
        )

    @classmethod
    def invalid_request(cls, message: str, **context) -> "TradeQueryApplicationException":
        """無効なリクエストの場合の例外

        Args:
            message: エラーメッセージ
            **context: 追加のコンテキスト情報

        Returns:
            TradeQueryApplicationException: アプリケーション例外
        """
        return cls(f"Invalid request: {message}", **context)
