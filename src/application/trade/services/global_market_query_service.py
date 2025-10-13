from typing import Optional
import logging

from src.domain.trade.repository.global_market_listing_read_model_repository import (
    GlobalMarketListingReadModelRepository,
    GlobalMarketFilter
)
from src.domain.common.exception import DomainException

from src.application.trade.contracts.global_market_dtos import (
    GlobalMarketFilterDto,
    GlobalMarketListingDto,
    GlobalMarketListDto
)
from src.application.trade.exceptions.trade_query_application_exception import TradeQueryApplicationException
from src.application.trade.util.cursor_codec import CursorCodec
from src.application.common.exceptions import SystemErrorException


class GlobalMarketQueryService:
    """グローバル取引所クエリサービス"""

    def __init__(self, global_market_listing_read_model_repository: GlobalMarketListingReadModelRepository):
        self._repository = global_market_listing_read_model_repository
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

    def get_market_listings(
        self,
        filter_dto: Optional[GlobalMarketFilterDto] = None,
        limit: int = 50,
        cursor: Optional[str] = None
    ) -> GlobalMarketListDto:
        """グローバル取引所の出品を取得（フィルタ適用・カーソルベースページング）

        Args:
            filter_dto: フィルタ条件DTO
            limit: 取得する最大件数
            cursor: ページングカーソル（Noneの場合は最初のページ）

        Returns:
            GlobalMarketListDto: 出品一覧DTO
        """
        # 入力バリデーション: limitは0より大きく100以下であること
        if limit <= 0 or limit > 100:
            raise TradeQueryApplicationException.invalid_filter(f"Limit must be between 1 and 100, got {limit}", limit=limit)

        return self._execute_with_error_handling(
            operation=lambda: self._get_market_listings_impl(filter_dto, limit, cursor),
            context={
                "action": "get_market_listings",
                "filter": filter_dto.__dict__ if filter_dto else None,
                "limit": limit,
                "cursor": cursor
            }
        )

    def _get_market_listings_impl(self, filter_dto: Optional[GlobalMarketFilterDto], limit: int, cursor: Optional[str]) -> GlobalMarketListDto:
        """グローバル取引所出品取得の実装"""
        # DTOからドメインフィルタに変換
        filter_condition = self._convert_to_filter(filter_dto)

        # カーソルをデコード
        domain_cursor = CursorCodec.decode_listing_cursor(cursor) if cursor else None

        # リポジトリからデータを取得
        listings, next_cursor = self._repository.find_listings(filter_condition, limit, domain_cursor)

        # ReadModelをDTOに変換
        listing_dtos = [self._convert_to_listing_dto(listing) for listing in listings]

        # next_cursorをencode
        next_cursor_encoded = CursorCodec.encode(next_cursor) if next_cursor else None

        return GlobalMarketListDto(
            listings=listing_dtos,
            next_cursor=next_cursor_encoded
        )

    def _convert_to_filter(self, filter_dto: Optional[GlobalMarketFilterDto]) -> GlobalMarketFilter:
        """DTOからドメインフィルタに変換"""
        if filter_dto is None:
            return GlobalMarketFilter()

        return GlobalMarketFilter(
            item_type=filter_dto.item_type,
            item_rarity=filter_dto.item_rarity,
            search_text=filter_dto.search_text,
            min_price=filter_dto.min_price,
            max_price=filter_dto.max_price
        )

    def _convert_to_listing_dto(self, read_model) -> GlobalMarketListingDto:
        """GlobalMarketListingReadModelをGlobalMarketListingDtoに変換"""
        return GlobalMarketListingDto(
            trade_id=int(read_model.trade_id),
            item_spec_id=int(read_model.item_spec_id),
            item_instance_id=int(read_model.item_instance_id),
            item_name=read_model.item_name,
            item_quantity=read_model.item_quantity,
            item_type=read_model.item_type.value,
            item_rarity=read_model.item_rarity.value,
            durability_current=read_model.durability_current,
            durability_max=read_model.durability_max,
            requested_gold=read_model.requested_gold
        )
