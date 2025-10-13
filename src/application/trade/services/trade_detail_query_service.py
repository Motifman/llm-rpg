import logging

from src.domain.trade.repository.trade_detail_read_model_repository import TradeDetailReadModelRepository
from src.domain.trade.repository.item_trade_statistics_read_model_repository import ItemTradeStatisticsReadModelRepository
from src.domain.trade.value_object.trade_id import TradeId
from src.domain.common.exception import DomainException

from src.application.trade.contracts.trade_detail_dtos import (
    TradeDetailDto,
    TradeStatisticsDto
)
from src.application.trade.exceptions.trade_query_application_exception import TradeQueryApplicationException
from src.application.common.exceptions import SystemErrorException


class TradeDetailQueryService:
    """取引詳細クエリサービス"""

    def __init__(
        self,
        trade_detail_read_model_repository: TradeDetailReadModelRepository,
        item_trade_statistics_read_model_repository: ItemTradeStatisticsReadModelRepository
    ):
        self._trade_detail_repository = trade_detail_read_model_repository
        self._statistics_repository = item_trade_statistics_read_model_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(self, operation, context: dict):
        """共通の例外処理を実行"""
        try:
            return operation()
        except TradeQueryApplicationException as e:
            # アプリケーション例外はそのまま再スロー
            raise e
        except DomainException as e:
            # ドメイン例外をアプリケーション例外に変換
            raise TradeQueryApplicationException.from_domain_error(e)
        except Exception as e:
            # 不明な例外はシステムエラーとしてログ出力し、SystemErrorExceptionをスロー
            self._logger.error(f"Unexpected error in {context.get('action', 'unknown')}: {str(e)}",
                             extra={'error_details': context})
            raise SystemErrorException(f"{context.get('action', 'unknown')} failed: {str(e)}",
                                     original_exception=e)

    def get_trade_detail(self, trade_id: int) -> TradeDetailDto:
        """取引詳細情報を取得

        Args:
            trade_id: 取引ID

        Returns:
            TradeDetailDto: 取引詳細DTO
        """
        # 入力バリデーション: trade_idは正の整数であること
        if trade_id <= 0:
            raise TradeQueryApplicationException.trade_not_found(trade_id)

        return self._execute_with_error_handling(
            operation=lambda: self._get_trade_detail_impl(trade_id),
            context={
                "action": "get_trade_detail",
                "trade_id": trade_id
            }
        )

    def _get_trade_detail_impl(self, trade_id: int) -> TradeDetailDto:
        """取引詳細取得の実装"""
        # ドメインオブジェクトに変換
        domain_trade_id = TradeId(trade_id)

        # 取引詳細を取得
        trade_detail = self._trade_detail_repository.find_detail(domain_trade_id)
        if trade_detail is None:
            raise TradeQueryApplicationException.trade_not_found(trade_id)

        # 統計情報を取得
        statistics = self._statistics_repository.find_statistics(trade_detail.item_spec_id)
        if statistics is None:
            raise TradeQueryApplicationException.item_statistics_not_found(int(trade_detail.item_spec_id))

        # DTOに変換
        statistics_dto = self._convert_to_statistics_dto(statistics)

        return TradeDetailDto(
            trade_id=int(trade_detail.trade_id),
            item_spec_id=int(trade_detail.item_spec_id),
            item_instance_id=int(trade_detail.item_instance_id),
            item_name=trade_detail.item_name,
            item_quantity=trade_detail.item_quantity,
            item_type=trade_detail.item_type.value,
            item_rarity=trade_detail.item_rarity.value,
            item_description=trade_detail.item_description,
            item_equipment_type=trade_detail.item_equipment_type.value if trade_detail.item_equipment_type else None,
            durability_current=trade_detail.durability_current,
            durability_max=trade_detail.durability_max,
            requested_gold=trade_detail.requested_gold,
            seller_name=trade_detail.seller_name,
            buyer_name=trade_detail.buyer_name,
            status=trade_detail.status,
            statistics=statistics_dto
        )

    def _convert_to_statistics_dto(self, read_model) -> TradeStatisticsDto:
        """ItemTradeStatisticsReadModelをTradeStatisticsDtoに変換"""
        return TradeStatisticsDto(
            min_price=read_model.min_price,
            max_price=read_model.max_price,
            avg_price=read_model.avg_price,
            median_price=read_model.median_price,
            total_trades=read_model.total_trades,
            success_rate=read_model.success_rate,
            last_updated=read_model.last_updated
        )
