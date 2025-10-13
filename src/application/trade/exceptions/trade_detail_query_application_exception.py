"""
TradeDetailQueryService専用のアプリケーション例外
"""

from typing import Optional
from src.domain.common.exception import DomainException
from src.application.common.exceptions import ApplicationException


class TradeDetailQueryApplicationException(ApplicationException):
    """TradeDetailQueryアプリケーション層例外"""

    @classmethod
    def from_domain_error(cls, e: DomainException) -> "TradeDetailQueryApplicationException":
        """ドメイン例外からの変換

        Args:
            e: ドメイン例外

        Returns:
            TradeDetailQueryApplicationException: 変換されたアプリケーション例外
        """
        return cls(f"Domain error in TradeDetailQuery usecase: {e.error_code}", cause=e)

    @classmethod
    def trade_not_found(cls, trade_id: int) -> "TradeDetailQueryApplicationException":
        """取引が見つからない場合の例外

        Args:
            trade_id: 取引ID

        Returns:
            TradeDetailQueryApplicationException: アプリケーション例外
        """
        return cls(
            f"Trade not found: {trade_id}",
            trade_id=trade_id
        )

    @classmethod
    def item_statistics_not_found(cls, item_spec_id: int) -> "TradeDetailQueryApplicationException":
        """アイテム統計情報が見つからない場合の例外

        Args:
            item_spec_id: アイテムスペックID

        Returns:
            TradeDetailQueryApplicationException: アプリケーション例外
        """
        return cls(
            f"Item statistics not found: {item_spec_id}",
            item_spec_id=item_spec_id
        )

    @classmethod
    def invalid_trade_id(cls, trade_id: int) -> "TradeDetailQueryApplicationException":
        """無効な取引IDの場合の例外

        Args:
            trade_id: 取引ID

        Returns:
            TradeDetailQueryApplicationException: アプリケーション例外
        """
        return cls(
            f"Invalid trade ID: {trade_id}",
            trade_id=trade_id
        )
