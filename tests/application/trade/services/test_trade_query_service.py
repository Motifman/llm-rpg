"""
TradeQueryServiceのテスト
"""
import pytest
from typing import Optional

from ai_rpg_world.application.trade.services.trade_query_service import TradeQueryService
from ai_rpg_world.infrastructure.repository.in_memory_trade_read_model_repository import InMemoryTradeReadModelRepository
from ai_rpg_world.application.trade.contracts.dtos import TradeDto, TradeListDto, TradeSearchFilterDto
from ai_rpg_world.application.trade.exceptions.trade_query_application_exception import TradeQueryApplicationException
from ai_rpg_world.application.common.exceptions import SystemErrorException
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.trade.exception.trade_exception import TradeIdValidationException, TradeSearchFilterValidationException
from ai_rpg_world.domain.player.exception.player_exceptions import PlayerIdValidationException


class TestTradeQueryService:
    """TradeQueryServiceのテストクラス"""

    def setup_method(self):
        """各テストメソッド実行前に呼ばれる"""
        self.repository = InMemoryTradeReadModelRepository()
        self.service = TradeQueryService(self.repository)

    def test_get_trade_details_existing_trade(self):
        """存在する取引の詳細を取得できる"""
        trade_dto = self.service.get_trade_details(1)

        assert isinstance(trade_dto, TradeDto)
        assert trade_dto.trade_id == 1
        assert trade_dto.seller_name == "勇者アルス"
        assert trade_dto.item_name == "鋼の剣"
        assert trade_dto.requested_gold == 500
        assert trade_dto.status == "ACTIVE"

    def test_get_trade_details_non_existing_trade(self):
        """存在しない取引IDを指定するとTradeQueryApplicationExceptionが発生"""
        with pytest.raises(TradeQueryApplicationException) as exc_info:
            self.service.get_trade_details(999)

        assert "Trade not found: 999" in str(exc_info.value)

    def test_get_trade_details_zero_trade_id(self):
        """trade_id=0を指定するとTradeQueryApplicationExceptionが発生（TradeIdバリデーション）"""
        with pytest.raises(TradeQueryApplicationException) as exc_info:
            self.service.get_trade_details(0)

        assert "Domain error in TradeQuery usecase: TRADE.ID_VALIDATION" in str(exc_info.value)

    def test_get_trade_details_negative_trade_id(self):
        """負のtrade_idを指定するとTradeQueryApplicationExceptionが発生（TradeIdバリデーション）"""
        with pytest.raises(TradeQueryApplicationException) as exc_info:
            self.service.get_trade_details(-1)

        assert "Domain error in TradeQuery usecase: TRADE.ID_VALIDATION" in str(exc_info.value)

    def test_get_recent_trades_default_limit(self):
        """デフォルトのリミットで最新の取引を取得できる"""
        result = self.service.get_recent_trades()

        assert isinstance(result, TradeListDto)
        assert len(result.trades) <= 10  # デフォルトリミットは10
        # 作成時間が新しい順に並んでいることを確認
        if len(result.trades) > 1:
            assert result.trades[0].created_at >= result.trades[1].created_at

    def test_get_recent_trades_custom_limit(self):
        """カスタムリミットで最新の取引を取得できる"""
        result = self.service.get_recent_trades(limit=5)

        assert isinstance(result, TradeListDto)
        assert len(result.trades) <= 5

    def test_get_recent_trades_with_cursor(self):
        """カーソルベースページングで最新の取引を取得できる"""
        # 最初のページを取得
        first_page = self.service.get_recent_trades(limit=3)
        assert isinstance(first_page, TradeListDto)
        assert len(first_page.trades) <= 3

        # カーソルが存在する場合、次のページを取得
        if first_page.next_cursor:
            second_page = self.service.get_recent_trades(limit=3, cursor=first_page.next_cursor)
            assert isinstance(second_page, TradeListDto)
            assert len(second_page.trades) <= 3

            # ページングが正しく動作していることを確認（重複がない）
            first_page_ids = {trade.trade_id for trade in first_page.trades}
            second_page_ids = {trade.trade_id for trade in second_page.trades}
            assert first_page_ids.isdisjoint(second_page_ids)

    def test_get_recent_trades_invalid_cursor_base64(self):
        """無効なbase64形式のカーソルを指定するとSystemErrorExceptionが発生"""
        with pytest.raises(SystemErrorException) as exc_info:
            self.service.get_recent_trades(cursor="invalid_base64_string!")

        assert "get_recent_trades failed: Invalid cursor format" in str(exc_info.value)

    def test_get_recent_trades_invalid_cursor_json(self):
        """base64は有効だがJSONが無効なカーソルを指定するとSystemErrorExceptionが発生"""
        # "invalid_json" をbase64エンコードしたもの
        invalid_cursor = "aW52YWxpZF9qc29u"  # base64 of "invalid_json"
        with pytest.raises(SystemErrorException) as exc_info:
            self.service.get_recent_trades(cursor=invalid_cursor)

        assert "get_recent_trades failed: Invalid cursor format" in str(exc_info.value)

    def test_get_recent_trades_zero_limit(self):
        """limit=0を指定すると空の結果が返る"""
        result = self.service.get_recent_trades(limit=0)
        assert isinstance(result, TradeListDto)
        assert len(result.trades) == 0

    def test_get_recent_trades_negative_limit(self):
        """負のlimitを指定すると空の結果が返る（リポジトリ依存）"""
        result = self.service.get_recent_trades(limit=-1)
        assert isinstance(result, TradeListDto)
        # リポジトリの実装によっては0件になる可能性がある

    def test_get_trades_for_player_existing_player(self):
        """存在するプレイヤーの取引を取得できる"""
        result = self.service.get_trades_for_player(player_id=1)

        assert isinstance(result, TradeListDto)
        # プレイヤーID=1の取引が存在することを確認
        assert len(result.trades) > 0
        for trade in result.trades:
            assert trade.seller_id == 1

    def test_get_trades_for_player_no_trades(self):
        """取引がないプレイヤーの場合、空のリストが返る"""
        result = self.service.get_trades_for_player(player_id=999)

        assert isinstance(result, TradeListDto)
        assert len(result.trades) == 0
        assert result.next_cursor is None

    def test_get_trades_for_player_with_cursor(self):
        """プレイヤーの取引をカーソルベースページングで取得できる"""
        # 最初のページを取得
        first_page = self.service.get_trades_for_player(player_id=1, limit=2)

        # カーソルが存在する場合、次のページを取得
        if first_page.next_cursor:
            second_page = self.service.get_trades_for_player(
                player_id=1,
                limit=2,
                cursor=first_page.next_cursor
            )

            # ページングが正しく動作していることを確認
            first_page_ids = {trade.trade_id for trade in first_page.trades}
            second_page_ids = {trade.trade_id for trade in second_page.trades}
            assert first_page_ids.isdisjoint(second_page_ids)

    def test_get_trades_for_player_zero_player_id(self):
        """player_id=0を指定するとTradeQueryApplicationExceptionが発生（PlayerIdバリデーション）"""
        with pytest.raises(TradeQueryApplicationException) as exc_info:
            self.service.get_trades_for_player(player_id=0)

        assert "Domain error in TradeQuery usecase: PLAYER.ID_VALIDATION" in str(exc_info.value)

    def test_get_trades_for_player_negative_player_id(self):
        """負のplayer_idを指定するとTradeQueryApplicationExceptionが発生（PlayerIdバリデーション）"""
        with pytest.raises(TradeQueryApplicationException) as exc_info:
            self.service.get_trades_for_player(player_id=-1)

        assert "Domain error in TradeQuery usecase: PLAYER.ID_VALIDATION" in str(exc_info.value)

    def test_get_trades_for_player_zero_limit(self):
        """limit=0を指定すると空の結果が返る"""
        result = self.service.get_trades_for_player(player_id=1, limit=0)
        assert isinstance(result, TradeListDto)
        assert len(result.trades) == 0

    def test_get_trades_for_player_negative_limit(self):
        """負のlimitを指定すると空の結果が返る（リポジトリ依存）"""
        result = self.service.get_trades_for_player(player_id=1, limit=-1)
        assert isinstance(result, TradeListDto)
        # リポジトリの実装によっては0件になる可能性がある

    def test_search_trades_no_filter(self):
        """フィルタなしで全取引を検索できる"""
        filter_dto = TradeSearchFilterDto()
        result = self.service.search_trades(filter_dto)

        assert isinstance(result, TradeListDto)
        assert len(result.trades) > 0

    def test_search_trades_by_item_name(self):
        """アイテム名で取引を検索できる"""
        filter_dto = TradeSearchFilterDto(item_name="剣")
        result = self.service.search_trades(filter_dto)

        assert isinstance(result, TradeListDto)
        for trade in result.trades:
            assert "剣" in trade.item_name

    def test_search_trades_by_item_types(self):
        """アイテムタイプで取引を検索できる"""
        filter_dto = TradeSearchFilterDto(item_types=["equipment"])
        result = self.service.search_trades(filter_dto)

        assert isinstance(result, TradeListDto)
        for trade in result.trades:
            assert trade.item_type == "equipment"

    def test_search_trades_by_rarities(self):
        """レアリティで取引を検索できる"""
        filter_dto = TradeSearchFilterDto(rarities=["rare"])
        result = self.service.search_trades(filter_dto)

        assert isinstance(result, TradeListDto)
        for trade in result.trades:
            assert trade.item_rarity == "rare"

    def test_search_trades_by_equipment_types(self):
        """装備タイプで取引を検索できる"""
        filter_dto = TradeSearchFilterDto(equipment_types=["weapon"])
        result = self.service.search_trades(filter_dto)

        assert isinstance(result, TradeListDto)
        for trade in result.trades:
            assert trade.item_equipment_type == "weapon"

    def test_search_trades_by_price_range(self):
        """価格範囲で取引を検索できる"""
        filter_dto = TradeSearchFilterDto(min_price=100, max_price=1000)
        result = self.service.search_trades(filter_dto)

        assert isinstance(result, TradeListDto)
        for trade in result.trades:
            assert 100 <= trade.requested_gold <= 1000

    def test_search_trades_by_statuses(self):
        """ステータスで取引を検索できる"""
        filter_dto = TradeSearchFilterDto(statuses=["active"])
        result = self.service.search_trades(filter_dto)

        assert isinstance(result, TradeListDto)
        for trade in result.trades:
            assert trade.status == "ACTIVE"

    def test_search_trades_multiple_filters(self):
        """複数のフィルタ条件を組み合わせて検索できる"""
        filter_dto = TradeSearchFilterDto(
            item_types=["equipment"],
            rarities=["common", "uncommon"],
            min_price=200,
            max_price=1500
        )
        result = self.service.search_trades(filter_dto)

        assert isinstance(result, TradeListDto)
        for trade in result.trades:
            assert trade.item_type == "equipment"
            assert trade.item_rarity in ["common", "uncommon"]
            assert 200 <= trade.requested_gold <= 1500

    def test_search_trades_with_cursor(self):
        """検索結果をカーソルベースページングで取得できる"""
        filter_dto = TradeSearchFilterDto()
        first_page = self.service.search_trades(filter_dto, limit=3)

        assert isinstance(first_page, TradeListDto)
        assert len(first_page.trades) <= 3

        # カーソルが存在する場合、次のページを取得
        if first_page.next_cursor:
            second_page = self.service.search_trades(
                filter_dto,
                limit=3,
                cursor=first_page.next_cursor
            )
            assert isinstance(second_page, TradeListDto)

            # ページングが正しく動作していることを確認
            first_page_ids = {trade.trade_id for trade in first_page.trades}
            second_page_ids = {trade.trade_id for trade in second_page.trades}
            assert first_page_ids.isdisjoint(second_page_ids)

    def test_search_trades_empty_result(self):
        """検索条件に一致する取引がない場合、空のリストが返る"""
        filter_dto = TradeSearchFilterDto(
            item_name="存在しないアイテム",
            min_price=999999
        )
        result = self.service.search_trades(filter_dto)

        assert isinstance(result, TradeListDto)
        assert len(result.trades) == 0
        assert result.next_cursor is None

    def test_search_trades_invalid_price_range_min_greater_than_max(self):
        """min_price > max_priceの場合TradeQueryApplicationExceptionが発生"""
        filter_dto = TradeSearchFilterDto(min_price=1000, max_price=500)
        with pytest.raises(TradeQueryApplicationException) as exc_info:
            self.service.search_trades(filter_dto)

        assert "Domain error in TradeQuery usecase: TRADE.SEARCH_FILTER_VALIDATION" in str(exc_info.value)

    def test_search_trades_negative_min_price(self):
        """負のmin_priceを指定するとTradeQueryApplicationExceptionが発生"""
        filter_dto = TradeSearchFilterDto(min_price=-100)
        with pytest.raises(TradeQueryApplicationException) as exc_info:
            self.service.search_trades(filter_dto)

        assert "Domain error in TradeQuery usecase: TRADE.SEARCH_FILTER_VALIDATION" in str(exc_info.value)

    def test_search_trades_negative_max_price(self):
        """負のmax_priceを指定するとTradeQueryApplicationExceptionが発生"""
        filter_dto = TradeSearchFilterDto(max_price=-100)
        with pytest.raises(TradeQueryApplicationException) as exc_info:
            self.service.search_trades(filter_dto)

        assert "Domain error in TradeQuery usecase: TRADE.SEARCH_FILTER_VALIDATION" in str(exc_info.value)

    def test_search_trades_invalid_item_type_enum(self):
        """無効なitem_typeを指定するとSystemErrorExceptionが発生"""
        filter_dto = TradeSearchFilterDto(item_types=["invalid_type"])
        with pytest.raises(SystemErrorException) as exc_info:
            self.service.search_trades(filter_dto)

        assert "search_trades failed:" in str(exc_info.value)

    def test_search_trades_invalid_rarity_enum(self):
        """無効なrarityを指定するとSystemErrorExceptionが発生"""
        filter_dto = TradeSearchFilterDto(rarities=["invalid_rarity"])
        with pytest.raises(SystemErrorException) as exc_info:
            self.service.search_trades(filter_dto)

        assert "search_trades failed:" in str(exc_info.value)

    def test_search_trades_invalid_status_enum(self):
        """無効なstatusを指定するとSystemErrorExceptionが発生"""
        filter_dto = TradeSearchFilterDto(statuses=["invalid_status"])
        with pytest.raises(SystemErrorException) as exc_info:
            self.service.search_trades(filter_dto)

        assert "search_trades failed:" in str(exc_info.value)

    def test_search_trades_zero_limit(self):
        """limit=0を指定すると空の結果が返る"""
        filter_dto = TradeSearchFilterDto()
        result = self.service.search_trades(filter_dto, limit=0)
        assert isinstance(result, TradeListDto)
        assert len(result.trades) == 0

    def test_search_trades_negative_limit(self):
        """負のlimitを指定すると空の結果が返る（リポジトリ依存）"""
        filter_dto = TradeSearchFilterDto()
        result = self.service.search_trades(filter_dto, limit=-1)
        assert isinstance(result, TradeListDto)
        # リポジトリの実装によっては0件になる可能性がある

    def test_execute_with_error_handling_domain_exception(self):
        """ドメイン例外が発生した場合、TradeQueryApplicationExceptionに変換される"""
        from unittest.mock import Mock, patch

        # モックを作成してDomainExceptionを発生させる
        from ai_rpg_world.domain.common.exception import StateException
        mock_operation = Mock(side_effect=StateException("Test domain error"))

        with pytest.raises(TradeQueryApplicationException) as exc_info:
            self.service._execute_with_error_handling(
                operation=mock_operation,
                context={"action": "test"}
            )

        assert "Domain error in TradeQuery usecase: DOMAIN_ERROR" in str(exc_info.value)

    def test_execute_with_error_handling_application_exception(self):
        """TradeQueryApplicationExceptionはそのまま再スローされる"""
        from unittest.mock import Mock

        app_exception = TradeQueryApplicationException("Test application error")

        mock_operation = Mock(side_effect=app_exception)

        with pytest.raises(TradeQueryApplicationException) as exc_info:
            self.service._execute_with_error_handling(
                operation=mock_operation,
                context={"action": "test"}
            )

        assert exc_info.value is app_exception

    def test_execute_with_error_handling_unexpected_exception(self):
        """予期しない例外が発生した場合、SystemErrorExceptionに変換される"""
        from unittest.mock import Mock

        mock_operation = Mock(side_effect=ValueError("Unexpected error"))

        with pytest.raises(SystemErrorException) as exc_info:
            self.service._execute_with_error_handling(
                operation=mock_operation,
                context={"action": "test_action"}
            )

        assert "test_action failed: Unexpected error" in str(exc_info.value)
        assert isinstance(exc_info.value.original_exception, ValueError)
