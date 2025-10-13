from typing import Optional
import logging

from src.domain.trade.repository.market_overview_read_model_repository import MarketOverviewReadModelRepository
from src.domain.common.exception import DomainException

from src.application.trade.contracts.market_overview_dtos import MarketOverviewDto
from src.application.trade.exceptions.market_overview_query_application_exception import MarketOverviewQueryApplicationException
from src.application.common.exceptions import SystemErrorException


class MarketOverviewQueryService:
    """市場全体概要クエリサービス"""

    def __init__(self, market_overview_read_model_repository: MarketOverviewReadModelRepository):
        self._market_overview_read_model_repository = market_overview_read_model_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(self, operation, context: dict):
        """共通の例外処理を実行"""
        try:
            return operation()
        except MarketOverviewQueryApplicationException as e:
            # アプリケーション例外はそのまま再スロー
            raise e
        except DomainException as e:
            # ドメイン例外をアプリケーション例外に変換
            raise MarketOverviewQueryApplicationException.from_domain_error(e)
        except Exception as e:
            # 不明な例外はシステムエラーとしてログ出力し、SystemErrorExceptionをスロー
            self._logger.error(f"Unexpected error in {context.get('action', 'unknown')}: {str(e)}",
                             extra={'error_details': context})
            raise SystemErrorException(f"{context.get('action', 'unknown')} failed: {str(e)}",
                                     original_exception=e)

    def get_market_overview(self) -> MarketOverviewDto:
        """市場全体の概要を取得"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_market_overview_impl(),
            context={
                "action": "get_market_overview"
            }
        )

    def _get_market_overview_impl(self) -> MarketOverviewDto:
        """市場概要取得の実装"""
        read_model = self._market_overview_read_model_repository.find_latest()
        if read_model is None:
            raise MarketOverviewQueryApplicationException.market_overview_not_found()

        return self._convert_to_dto(read_model)

    def _convert_to_dto(self, read_model) -> MarketOverviewDto:
        """MarketOverviewReadModelをMarketOverviewDtoに変換"""
        return MarketOverviewDto(
            total_active_listings=read_model.total_active_listings,
            total_completed_trades_today=read_model.total_completed_trades_today,
            average_success_rate=read_model.average_success_rate,
            top_traded_items=read_model.top_traded_items,
            last_updated=read_model.last_updated
        )
