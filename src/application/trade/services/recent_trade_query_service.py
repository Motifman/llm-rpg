from typing import Optional
import logging

from src.domain.trade.repository.recent_trade_read_model_repository import RecentTradeReadModelRepository
from src.domain.common.exception import DomainException

from src.application.trade.contracts.recent_trade_dtos import RecentTradeDto, RecentTradeSummaryDto
from src.application.trade.exceptions.recent_trade_query_application_exception import RecentTradeQueryApplicationException
from src.application.common.exceptions import SystemErrorException


class RecentTradeQueryService:
    """最近取引履歴クエリサービス"""

    def __init__(self, recent_trade_read_model_repository: RecentTradeReadModelRepository):
        self._recent_trade_read_model_repository = recent_trade_read_model_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(self, operation, context: dict):
        """共通の例外処理を実行"""
        try:
            return operation()
        except RecentTradeQueryApplicationException as e:
            # アプリケーション例外はそのまま再スロー
            raise e
        except DomainException as e:
            # ドメイン例外をアプリケーション例外に変換
            raise RecentTradeQueryApplicationException.from_domain_error(e)
        except Exception as e:
            # 不明な例外はシステムエラーとしてログ出力し、SystemErrorExceptionをスロー
            self._logger.error(f"Unexpected error in {context.get('action', 'unknown')}: {str(e)}",
                             extra={'error_details': context})
            raise SystemErrorException(f"{context.get('action', 'unknown')} failed: {str(e)}",
                                     original_exception=e)

    def get_recent_trades(self, item_name: str) -> RecentTradeDto:
        """指定アイテムの最近取引履歴を取得"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_recent_trades_impl(item_name),
            context={
                "action": "get_recent_trades",
                "item_name": item_name
            }
        )

    def _get_recent_trades_impl(self, item_name: str) -> RecentTradeDto:
        """最近取引履歴取得の実装"""
        read_model = self._recent_trade_read_model_repository.find_by_item_name(item_name)
        if read_model is None:
            raise RecentTradeQueryApplicationException.recent_trades_not_found(item_name)

        return self._convert_to_dto(read_model)

    def _convert_to_dto(self, read_model) -> RecentTradeDto:
        """RecentTradeReadModelをRecentTradeDtoに変換"""
        trades = [
            RecentTradeSummaryDto(
                trade_id=trade_data.trade_id,
                item_name=read_model.item_name,
                price=trade_data.price,
                traded_at=trade_data.traded_at
            )
            for trade_data in read_model.recent_trades
        ]

        return RecentTradeDto(
            item_name=read_model.item_name,
            trades=trades
        )
