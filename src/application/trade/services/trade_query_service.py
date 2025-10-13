from typing import Optional
import logging

from src.domain.trade.value_object.trade_id import TradeId
from src.domain.trade.value_object.trade_search_filter import TradeSearchFilter
from src.domain.trade.repository.trade_read_model_repository import TradeReadModelRepository
from src.domain.player.value_object.player_id import PlayerId
from src.domain.common.exception import DomainException

from src.application.trade.contracts.dtos import TradeDto, TradeListDto, TradeSearchFilterDto
from src.application.trade.exceptions.trade_query_application_exception import TradeQueryApplicationException
from src.application.trade.util.trade_cursor_codec import TradeCursorCodec
from src.application.common.exceptions import SystemErrorException


class TradeQueryService:
    """取引検索サービス"""

    def __init__(self, trade_read_model_repository: TradeReadModelRepository):
        self._trade_read_model_repository = trade_read_model_repository
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

    def get_trade_details(self, trade_id: int) -> TradeDto:
        """取引詳細を取得"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_trade_details_impl(trade_id),
            context={
                "action": "get_trade_details",
                "trade_id": trade_id
            }
        )

    def _get_trade_details_impl(self, trade_id: int) -> TradeDto:
        """取引詳細取得の実装"""
        trade_read_model = self._trade_read_model_repository.find_by_id(TradeId(trade_id))
        if trade_read_model is None:
            raise TradeQueryApplicationException.trade_not_found(str(trade_id))

        return self._convert_to_dto(trade_read_model)

    def get_recent_trades(self, limit: int = 10, cursor: Optional[str] = None) -> TradeListDto:
        """最新の取引を取得（カーソルベースページング）"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_recent_trades_impl(limit, cursor),
            context={
                "action": "get_recent_trades",
                "limit": limit,
                "cursor": cursor
            }
        )

    def _get_recent_trades_impl(self, limit: int, cursor: Optional[str]) -> TradeListDto:
        """最新取引取得の実装"""
        # カーソルをデコード
        domain_cursor = TradeCursorCodec.decode(cursor) if cursor else None

        trade_read_models, next_cursor = self._trade_read_model_repository.find_recent_trades(limit, domain_cursor)
        trades = [self._convert_to_dto(model) for model in trade_read_models]

        # next_cursorをencode
        next_cursor_encoded = TradeCursorCodec.encode(next_cursor) if next_cursor else None

        return TradeListDto(
            trades=trades,
            next_cursor=next_cursor_encoded
        )

    def get_trades_for_player(self, player_id: int, limit: int = 10, cursor: Optional[str] = None) -> TradeListDto:
        """プレイヤー宛の取引を取得（カーソルベースページング）"""
        return self._execute_with_error_handling(
            operation=lambda: self._get_trades_for_player_impl(player_id, limit, cursor),
            context={
                "action": "get_trades_for_player",
                "player_id": player_id,
                "limit": limit,
                "cursor": cursor
            }
        )

    def _get_trades_for_player_impl(self, player_id: int, limit: int, cursor: Optional[str]) -> TradeListDto:
        """プレイヤー宛取引取得の実装"""
        # カーソルをデコード
        domain_cursor = TradeCursorCodec.decode(cursor) if cursor else None

        trade_read_models, next_cursor = self._trade_read_model_repository.find_trades_for_player(PlayerId(player_id), limit, domain_cursor)
        trades = [self._convert_to_dto(model) for model in trade_read_models]

        # next_cursorをencode
        next_cursor_encoded = TradeCursorCodec.encode(next_cursor) if next_cursor else None

        return TradeListDto(
            trades=trades,
            next_cursor=next_cursor_encoded
        )

    def search_trades(self, filter_dto: TradeSearchFilterDto, limit: int = 20,
                     cursor: Optional[str] = None) -> TradeListDto:
        """フィルタ条件で取引を検索"""
        return self._execute_with_error_handling(
            operation=lambda: self._search_trades_impl(filter_dto, limit, cursor),
            context={
                "action": "search_trades",
                "filter": filter_dto,
                "limit": limit,
                "cursor": cursor
            }
        )

    def _search_trades_impl(self, filter_dto: TradeSearchFilterDto, limit: int,
                           cursor: Optional[str]) -> TradeListDto:
        """フィルタ検索の実装"""
        # DTOからドメインValue Objectを作成（従来パターン維持）
        domain_filter = TradeSearchFilter.from_primitives(
            item_name=filter_dto.item_name,
            item_types=filter_dto.item_types,
            rarities=filter_dto.rarities,
            equipment_types=filter_dto.equipment_types,
            min_price=filter_dto.min_price,
            max_price=filter_dto.max_price,
            statuses=filter_dto.statuses
        )

        domain_cursor = TradeCursorCodec.decode(cursor) if cursor else None

        # リポジトリの検索メソッドにフィルタを渡す
        trade_read_models, next_cursor = self._trade_read_model_repository.search_trades(
            domain_filter, limit, domain_cursor
        )

        trades = [self._convert_to_dto(model) for model in trade_read_models]
        next_cursor_encoded = TradeCursorCodec.encode(next_cursor) if next_cursor else None

        return TradeListDto(
            trades=trades,
            next_cursor=next_cursor_encoded
        )

    def _convert_to_dto(self, read_model) -> TradeDto:
        """TradeReadModelをTradeDtoに変換"""
        return TradeDto(
            trade_id=read_model.trade_id,
            seller_id=read_model.seller_id,
            seller_name=read_model.seller_name,
            buyer_id=read_model.buyer_id,
            buyer_name=read_model.buyer_name,
            requested_gold=read_model.requested_gold,
            status=read_model.status,
            created_at=read_model.created_at,
            item_instance_id=read_model.item_instance_id,
            item_name=read_model.item_name,
            item_quantity=read_model.item_quantity,
            item_type=read_model.item_type,
            item_rarity=read_model.item_rarity,
            item_description=read_model.item_description,
            item_equipment_type=read_model.item_equipment_type,
            durability_current=read_model.durability_current,
            durability_max=read_model.durability_max
        )
