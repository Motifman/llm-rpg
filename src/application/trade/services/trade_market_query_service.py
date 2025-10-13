from typing import Optional
import logging

from src.domain.trade.repository.trade_market_read_model_repository import TradeMarketReadModelRepository
from src.domain.common.exception import DomainException

from src.application.trade.contracts.market_dtos import (
    ItemMarketDto,
    ItemMarketListDto,
    PriceStatisticsDto,
    TradeStatisticsDto
)
from src.application.trade.exceptions.trade_market_query_application_exception import TradeMarketQueryApplicationException
from src.application.common.exceptions import SystemErrorException


class TradeMarketQueryService:
    """取引相場・統計情報クエリサービス"""

    def __init__(self, trade_market_read_model_repository: TradeMarketReadModelRepository):
        self._trade_market_read_model_repository = trade_market_read_model_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(self, operation, context: dict):
        """共通の例外処理を実行"""
        try:
            return operation()
        except TradeMarketQueryApplicationException as e:
            # アプリケーション例外はそのまま再スロー
            raise e
        except DomainException as e:
            # ドメイン例外をアプリケーション例外に変換
            raise TradeMarketQueryApplicationException.from_domain_error(e)
        except Exception as e:
            # 不明な例外はシステムエラーとしてログ出力し、SystemErrorExceptionをスロー
            self._logger.error(f"Unexpected error in {context.get('action', 'unknown')}: {str(e)}",
                             extra={'error_details': context})
            raise SystemErrorException(f"{context.get('action', 'unknown')} failed: {str(e)}",
                                     original_exception=e)

    def get_item_market_info(self, item_name: str) -> ItemMarketDto:
        """アイテムの市場情報を取得"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_item_market_info_impl(item_name),
            context={
                "action": "get_item_market_info",
                "item_name": item_name
            }
        )

    def _get_item_market_info_impl(self, item_name: str) -> ItemMarketDto:
        """アイテム市場情報取得の実装"""
        read_model = self._trade_market_read_model_repository.find_by_item_name(item_name)
        if read_model is None:
            raise TradeMarketQueryApplicationException.item_not_found(item_name)

        return self._convert_to_dto(read_model)

    def get_popular_items_market(self, limit: int = 10) -> ItemMarketListDto:
        """人気アイテムの市場情報を取得（取引量順）"""
        # 入力バリデーション: limitは0以上の整数であること
        if limit < 0:
            raise TradeMarketQueryApplicationException.invalid_limit(limit)

        return self._execute_with_error_handling(
            operation=lambda: self._get_popular_items_market_impl(limit),
            context={
                "action": "get_popular_items_market",
                "limit": limit
            }
        )

    def _get_popular_items_market_impl(self, limit: int) -> ItemMarketListDto:
        """人気アイテム市場情報取得の実装"""
        read_models = self._trade_market_read_model_repository.find_popular_items(limit)
        items = [self._convert_to_dto(model) for model in read_models]

        return ItemMarketListDto(
            items=items,
            total_count=len(items)
        )

    def _convert_to_dto(self, read_model) -> ItemMarketDto:
        """TradeMarketReadModelをItemMarketDtoに変換"""
        return ItemMarketDto(
            item_spec_id=int(read_model.item_spec_id),
            item_name=read_model.item_name,
            item_type=read_model.item_type,
            item_rarity=read_model.item_rarity,
            price_stats=PriceStatisticsDto(
                current_market_price=read_model.current_market_price,
                min_price=read_model.min_price,
                max_price=read_model.max_price,
                avg_price=read_model.avg_price,
                median_price=read_model.median_price
            ),
            trade_stats=TradeStatisticsDto(
                total_trades=read_model.total_trades,
                active_listings=read_model.active_listings,
                completed_trades=read_model.completed_trades,
                success_rate=read_model.success_rate,
                last_updated=read_model.last_updated
            )
        )
