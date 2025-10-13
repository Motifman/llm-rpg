from typing import Optional
import logging

from src.domain.trade.repository.personal_trade_listing_read_model_repository import (
    PersonalTradeListingReadModelRepository,
    PersonalTradePageSpec
)
from src.domain.player.value_object.player_id import PlayerId
from src.domain.common.exception import DomainException

from src.application.trade.contracts.personal_trade_dtos import (
    PersonalTradeListingDto,
    PersonalTradeListDto
)
from src.application.trade.exceptions.trade_query_application_exception import TradeQueryApplicationException
from src.application.common.exceptions import SystemErrorException


class PersonalTradeQueryService:
    """個人取引クエリサービス"""

    def __init__(self, personal_trade_listing_read_model_repository: PersonalTradeListingReadModelRepository):
        self._repository = personal_trade_listing_read_model_repository
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

    def get_personal_trades(self, player_id: int, limit: int = 20) -> PersonalTradeListDto:
        """プレイヤー宛の取引を取得

        Args:
            player_id: プレイヤーID
            limit: 取得する最大件数

        Returns:
            PersonalTradeListDto: 個人取引一覧DTO
        """
        # 入力バリデーション: player_idは正の整数であること
        if player_id <= 0:
            raise TradeQueryApplicationException.invalid_player_id(player_id)

        # 入力バリデーション: limitは0より大きく50以下であること
        if limit <= 0 or limit > 50:
            raise TradeQueryApplicationException.invalid_filter(f"Limit must be between 1 and 50, got {limit}", limit=limit)

        return self._execute_with_error_handling(
            operation=lambda: self._get_personal_trades_impl(player_id, limit),
            context={
                "action": "get_personal_trades",
                "player_id": player_id,
                "limit": limit
            }
        )

    def _get_personal_trades_impl(self, player_id: int, limit: int) -> PersonalTradeListDto:
        """個人取引取得の実装"""
        # ドメインオブジェクトに変換
        domain_player_id = PlayerId(player_id)
        page_spec = PersonalTradePageSpec(limit=limit, offset=0)

        # リポジトリからデータを取得
        listings, has_next_page = self._repository.find_for_player(domain_player_id, page_spec)

        # ReadModelをDTOに変換
        listing_dtos = [self._convert_to_listing_dto(listing) for listing in listings]

        return PersonalTradeListDto(
            listings=listing_dtos,
            total_count=len(listing_dtos),
            has_next_page=has_next_page
        )

    def _convert_to_listing_dto(self, read_model) -> PersonalTradeListingDto:
        """PersonalTradeListingReadModelをPersonalTradeListingDtoに変換"""
        return PersonalTradeListingDto(
            trade_id=int(read_model.trade_id),
            item_spec_id=int(read_model.item_spec_id),
            item_instance_id=int(read_model.item_instance_id),
            item_name=read_model.item_name,
            item_quantity=read_model.item_quantity,
            item_type=read_model.item_type.value,
            item_rarity=read_model.item_rarity.value,
            durability_current=read_model.durability_current,
            durability_max=read_model.durability_max,
            requested_gold=read_model.requested_gold,
            seller_name=read_model.seller_name
        )
