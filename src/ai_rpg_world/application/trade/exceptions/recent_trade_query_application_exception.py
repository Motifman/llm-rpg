"""
RecentTradeQueryService専用のアプリケーション例外
"""

from typing import Optional
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.application.common.exceptions import ApplicationException


class RecentTradeQueryApplicationException(ApplicationException):
    """RecentTradeQueryアプリケーション層例外"""

    @classmethod
    def from_domain_error(cls, e: DomainException) -> "RecentTradeQueryApplicationException":
        """ドメイン例外からの変換

        Args:
            e: ドメイン例外

        Returns:
            RecentTradesQueryApplicationException: 変換されたアプリケーション例外
        """
        return cls(f"Domain error in RecentTradeQuery usecase: {e.error_code}", cause=e)

    @classmethod
    def recent_trades_not_found(cls, item_name: str) -> "RecentTradeQueryApplicationException":
        """最近の取引履歴が見つからない場合の例外

        Args:
            item_name: アイテム名

        Returns:
            RecentTradesQueryApplicationException: アプリケーション例外
        """
        return cls(
            f"Recent trades information not found: {item_name}",
            item_name=item_name
        )

    @classmethod
    def invalid_request(cls, message: str, **context) -> "RecentTradeQueryApplicationException":
        """無効なリクエストの場合の例外

        Args:
            message: エラーメッセージ
            **context: 追加のコンテキスト情報

        Returns:
            RecentTradesQueryApplicationException: アプリケーション例外
        """
        return cls(f"Invalid request: {message}", **context)
