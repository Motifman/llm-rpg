"""
TradeQueryService専用のアプリケーション例外
"""

from typing import Optional
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.application.common.exceptions import ApplicationException


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
    def trade_not_found(cls, trade_id: int) -> "TradeQueryApplicationException":
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
    def invalid_player_id(cls, player_id: int) -> "TradeQueryApplicationException":
        """無効なプレイヤーIDの場合の例外

        Args:
            player_id: プレイヤーID

        Returns:
            TradeQueryApplicationException: アプリケーション例外
        """
        return cls(
            f"Invalid player ID: {player_id}",
            player_id=player_id
        )

    @classmethod
    def item_statistics_not_found(cls, item_spec_id: int) -> "TradeQueryApplicationException":
        """アイテム統計情報が見つからない場合の例外

        Args:
            item_spec_id: アイテムスペックID

        Returns:
            TradeQueryApplicationException: アプリケーション例外
        """
        return cls(
            f"Item statistics not found: {item_spec_id}",
            item_spec_id=item_spec_id
        )

    @classmethod
    def invalid_filter(cls, message: str, **context) -> "TradeQueryApplicationException":
        """無効なフィルタ条件の場合の例外

        Args:
            message: エラーメッセージ
            **context: 追加のコンテキスト情報

        Returns:
            TradeQueryApplicationException: アプリケーション例外
        """
        return cls(f"Invalid filter: {message}", **context)