import logging
from collections.abc import Callable
from typing import Any, TypeVar

from ai_rpg_world.application.common.exceptions import SystemErrorException
from ai_rpg_world.application.trade.contracts.global_market_dtos import (
    GlobalMarketFilterDto,
    GlobalMarketListDto,
    GlobalMarketListingDto,
)
from ai_rpg_world.application.trade.exceptions.global_market_query_application_exception import (
    GlobalMarketQueryApplicationException,
)
from ai_rpg_world.application.trade.util.cursor_codec import CursorCodec
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus
from ai_rpg_world.domain.trade.repository.global_market_listing_read_model_repository import (
    GlobalMarketListingReadModelRepository,
)
from ai_rpg_world.domain.trade.value_object.trade_search_filter import TradeSearchFilter

_Result = TypeVar("_Result")


class GlobalMarketQueryService:
    """グローバル取引所クエリサービス"""

    def __init__(self, global_market_listing_read_model_repository: GlobalMarketListingReadModelRepository):
        self._repository = global_market_listing_read_model_repository
        self._logger = logging.getLogger(self.__class__.__name__)

    def _execute_with_error_handling(
        self, operation: Callable[[], _Result], context: dict[str, Any]
    ) -> _Result:
        """共通の例外処理を実行"""
        try:
            return operation()
        except GlobalMarketQueryApplicationException as e:
            # アプリケーション例外はそのまま再スロー
            raise e
        except DomainException as e:
            # ドメイン例外をアプリケーション例外に変換
            raise GlobalMarketQueryApplicationException.from_domain_error(e)
        except Exception as e:
            # 不明な例外はシステムエラーとしてログ出力し、SystemErrorExceptionをスロー
            self._logger.error(f"Unexpected error in {context.get('action', 'unknown')}: {e!s}",
                             extra={'error_details': context})
            raise SystemErrorException(f"{context.get('action', 'unknown')} failed: {e!s}",
                                     original_exception=e)

    def get_market_listings(
        self,
        filter_dto: GlobalMarketFilterDto | None = None,
        limit: int = 50,
        cursor: str | None = None
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
            raise GlobalMarketQueryApplicationException.invalid_filter(f"Limit must be between 1 and 100, got {limit}", limit=limit)

        return self._execute_with_error_handling(
            operation=lambda: self._get_market_listings_impl(filter_dto, limit, cursor),
            context={
                "action": "get_market_listings",
                "filter": filter_dto.__dict__ if filter_dto else None,
                "limit": limit,
                "cursor": cursor
            }
        )

    def _get_market_listings_impl(self, filter_dto: GlobalMarketFilterDto | None, limit: int, cursor: str | None) -> GlobalMarketListDto:
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

    def _convert_to_filter(self, filter_dto: GlobalMarketFilterDto | None) -> TradeSearchFilter:
        """DTOからドメインフィルタに変換"""
        # グローバル取引所では常にアクティブな取引のみを表示
        base_statuses = [TradeStatus.ACTIVE.value]

        if filter_dto is None:
            return TradeSearchFilter.from_primitives(statuses=base_statuses)

        return TradeSearchFilter.from_primitives(
            item_name=filter_dto.item_name,
            item_types=filter_dto.item_types,
            rarities=filter_dto.rarities,
            equipment_types=filter_dto.equipment_types,
            min_price=filter_dto.min_price,
            max_price=filter_dto.max_price,
            statuses=base_statuses  # グローバル取引所では常にACTIVEステータスのみ
        )

    def _convert_to_listing_dto(self, read_model: Any) -> GlobalMarketListingDto:
        """GlobalMarketListingReadModelをGlobalMarketListingDtoに変換"""
        return GlobalMarketListingDto(
            trade_id=int(read_model.trade_id),
            item_spec_id=int(read_model.item_spec_id),
            item_instance_id=int(read_model.item_instance_id),
            item_name=read_model.item_name,
            item_quantity=read_model.item_quantity,
            item_type=read_model.item_type.value,
            item_rarity=read_model.item_rarity.value,
            item_equipment_type=read_model.item_equipment_type.value if read_model.item_equipment_type else None,
            status=read_model.status.value,
            created_at=read_model.created_at.isoformat(),
            durability_current=read_model.durability_current,
            durability_max=read_model.durability_max,
            requested_gold=read_model.requested_gold
        )
