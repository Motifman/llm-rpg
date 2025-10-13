"""
TradeMarketQueryServiceのテスト
"""
import pytest
from datetime import datetime, timedelta
from unittest.mock import patch

from src.application.trade.services.trade_market_query_service import TradeMarketQueryService
from src.infrastructure.repository.in_memory_trade_market_read_model_repository import InMemoryTradeMarketReadModelRepository
from src.application.trade.contracts.market_dtos import ItemMarketDto, ItemMarketListDto, PriceStatisticsDto, TradeStatisticsDto
from src.application.trade.exceptions.trade_market_query_application_exception import TradeMarketQueryApplicationException
from src.application.common.exceptions import SystemErrorException
from src.domain.common.exception import DomainException
from src.domain.item.value_object.item_spec_id import ItemSpecId


class TestTradeMarketQueryService:
    """TradeMarketQueryServiceのテスト"""

    def setup_method(self):
        """各テストメソッド実行前のセットアップ"""
        self.repository = InMemoryTradeMarketReadModelRepository()
        self.service = TradeMarketQueryService(self.repository)

    def test_get_item_market_info_success(self):
        """get_item_market_info - 正常系テスト"""
        # 存在するアイテムのテスト
        result = self.service.get_item_market_info("伝説の剣")

        assert isinstance(result, ItemMarketDto)
        assert result.item_name == "伝説の剣"
        assert result.item_type == "weapon"
        assert result.item_rarity == "legendary"
        assert result.item_spec_id == 1

        # 価格統計の検証
        assert result.price_stats.current_market_price == 50000
        assert result.price_stats.min_price == 45000
        assert result.price_stats.max_price == 55000
        assert result.price_stats.avg_price == 48500.0
        assert result.price_stats.median_price == 48000

        # 取引統計の検証
        assert result.trade_stats.total_trades == 150
        assert result.trade_stats.active_listings == 12
        assert result.trade_stats.completed_trades == 145
        assert result.trade_stats.success_rate == 0.967
        assert isinstance(result.trade_stats.last_updated, datetime)

    def test_get_item_market_info_different_items(self):
        """get_item_market_info - 異なるアイテムのテスト"""
        # 別のアイテムをテスト
        result = self.service.get_item_market_info("ヒーリングポーション")

        assert result.item_name == "ヒーリングポーション"
        assert result.item_type == "consumable"
        assert result.item_rarity == "common"
        assert result.item_spec_id == 4
        assert result.price_stats.current_market_price == 100

    def test_get_item_market_info_item_not_found(self):
        """get_item_market_info - 存在しないアイテムの場合"""
        with pytest.raises(TradeMarketQueryApplicationException) as exc_info:
            self.service.get_item_market_info("存在しないアイテム")

        assert "Item market information not found: 存在しないアイテム" in str(exc_info.value)
        assert exc_info.value.context["item_name"] == "存在しないアイテム"

    def test_get_popular_items_market_default_limit(self):
        """get_popular_items_market - デフォルトlimitでのテスト"""
        result = self.service.get_popular_items_market()

        assert isinstance(result, ItemMarketListDto)
        assert len(result.items) == 10  # デフォルトlimitは10
        assert result.total_count == 10

        # 取引量で降順にソートされていることを確認
        for i in range(len(result.items) - 1):
            assert result.items[i].trade_stats.total_trades >= result.items[i + 1].trade_stats.total_trades

    def test_get_popular_items_market_custom_limit(self):
        """get_popular_items_market - カスタムlimitでのテスト"""
        # limit=5のテスト
        result = self.service.get_popular_items_market(limit=5)

        assert len(result.items) == 5
        assert result.total_count == 5

        # limit=1のテスト
        result = self.service.get_popular_items_market(limit=1)
        assert len(result.items) == 1
        assert result.total_count == 1

        # 最も取引量の多いアイテムが返されることを確認
        assert result.items[0].item_name == "石ころ"  # 500取引

    def test_get_popular_items_market_large_limit(self):
        """get_popular_items_market - アイテム数以上のlimitでのテスト"""
        # 現在のサンプルデータは15アイテムなので、20を指定
        result = self.service.get_popular_items_market(limit=20)

        assert len(result.items) == 15  # 全アイテム数
        assert result.total_count == 15

    def test_get_popular_items_market_zero_limit(self):
        """get_popular_items_market - limit=0のテスト"""
        result = self.service.get_popular_items_market(limit=0)

        assert len(result.items) == 0
        assert result.total_count == 0

    def test_convert_to_dto(self):
        """_convert_to_dto - DTO変換のテスト"""
        # リポジトリからモデルを取得
        read_model = self.repository.find_by_item_name("伝説の剣")
        assert read_model is not None

        # 変換メソッドを直接テスト
        result = self.service._convert_to_dto(read_model)

        assert isinstance(result, ItemMarketDto)
        assert result.item_spec_id == int(read_model.item_spec_id)
        assert result.item_name == read_model.item_name
        assert result.item_type == read_model.item_type
        assert result.item_rarity == read_model.item_rarity

        # PriceStatisticsDtoの検証
        assert isinstance(result.price_stats, PriceStatisticsDto)
        assert result.price_stats.current_market_price == read_model.current_market_price
        assert result.price_stats.min_price == read_model.min_price
        assert result.price_stats.max_price == read_model.max_price
        assert result.price_stats.avg_price == read_model.avg_price
        assert result.price_stats.median_price == read_model.median_price

        # TradeStatisticsDtoの検証
        assert isinstance(result.trade_stats, TradeStatisticsDto)
        assert result.trade_stats.total_trades == read_model.total_trades
        assert result.trade_stats.active_listings == read_model.active_listings
        assert result.trade_stats.completed_trades == read_model.completed_trades
        assert result.trade_stats.success_rate == read_model.success_rate
        assert result.trade_stats.last_updated == read_model.last_updated

    def test_execute_with_error_handling_success(self):
        """_execute_with_error_handling - 正常系のテスト"""
        def successful_operation():
            return "success"

        result = self.service._execute_with_error_handling(
            operation=successful_operation,
            context={"action": "test_action", "param": "test_value"}
        )

        assert result == "success"

    def test_execute_with_error_handling_trade_market_query_exception(self):
        """_execute_with_error_handling - TradeMarketQueryApplicationExceptionのテスト"""
        def failing_operation():
            raise TradeMarketQueryApplicationException("Test error", test_param="test_value")

        with pytest.raises(TradeMarketQueryApplicationException) as exc_info:
            self.service._execute_with_error_handling(
                operation=failing_operation,
                context={"action": "test_action"}
            )

        assert str(exc_info.value) == "Test error"
        assert exc_info.value.context["test_param"] == "test_value"

    def test_execute_with_error_handling_domain_exception(self):
        """_execute_with_error_handling - DomainExceptionのテスト"""
        class TestDomainException(DomainException):
            error_code = "DOMAIN_ERROR"
            category = DomainException.category

        def failing_operation():
            raise TestDomainException("Domain error occurred", domain_param="domain_value")

        with pytest.raises(TradeMarketQueryApplicationException) as exc_info:
            self.service._execute_with_error_handling(
                operation=failing_operation,
                context={"action": "test_action"}
            )

        assert "Domain error in TradeMarketQuery usecase: DOMAIN_ERROR" in str(exc_info.value)

    def test_execute_with_error_handling_unexpected_exception(self):
        """_execute_with_error_handling - 予期しない例外のテスト"""
        def failing_operation():
            raise ValueError("Unexpected error")

        with pytest.raises(SystemErrorException) as exc_info:
            self.service._execute_with_error_handling(
                operation=failing_operation,
                context={"action": "test_action", "param": "test_value"}
            )

        assert "test_action failed: Unexpected error" in str(exc_info.value)
        assert isinstance(exc_info.value.original_exception, ValueError)

    def test_execute_with_error_handling_empty_context(self):
        """_execute_with_error_handling - 空のコンテキストでのテスト"""
        def failing_operation():
            raise ValueError("Test error")

        with pytest.raises(SystemErrorException) as exc_info:
            self.service._execute_with_error_handling(
                operation=failing_operation,
                context={}
            )

        assert "unknown failed: Test error" in str(exc_info.value)


    def test_integration_get_item_market_info_with_repository_error(self):
        """統合テスト - リポジトリエラー時のget_item_market_info"""
        # リポジトリをクリアして空の状態にする
        self.repository.clear()

        with pytest.raises(TradeMarketQueryApplicationException) as exc_info:
            self.service.get_item_market_info("伝説の剣")

        assert "Item market information not found: 伝説の剣" in str(exc_info.value)

    def test_integration_get_popular_items_market_with_repository_error(self):
        """統合テスト - リポジトリエラー時のget_popular_items_market"""
        # リポジトリをクリア
        self.repository.clear()

        result = self.service.get_popular_items_market(limit=5)

        # 空のリポジトリでも正常に動作し、空のリストを返す
        assert isinstance(result, ItemMarketListDto)
        assert len(result.items) == 0
        assert result.total_count == 0

    def test_popular_items_ordering_verification(self):
        """人気アイテムの順序検証テスト"""
        result = self.service.get_popular_items_market(limit=20)

        # 手動で期待される順序を確認（取引量降順）
        expected_order = [
            ("石ころ", 500),  # total_trades: 500
            ("ヒーリングポーション", 200),  # 200
            ("マナポーション", 180),  # 180
            ("伝説の剣", 150),  # 150
            ("幸運の指輪", 95),  # 95
            ("鉄の剣", 80),  # 80
            ("ミスリルのインゴット", 60),  # 60
            ("革の鎧", 45),  # 45
            ("エルフの弓", 35),  # 35
            ("ドラゴンスケールアーマー", 25),  # 25
            ("雷神の槌", 20),  # 20
            ("呪いのアミュレット", 12),  # 12
            ("魔法のクリスタル", 8),  # 8
            ("神聖な聖杯", 5),  # 5
            ("未知の鉱石", 0),  # 0
        ]

        for i, (expected_name, expected_trades) in enumerate(expected_order[:len(result.items)]):
            assert result.items[i].item_name == expected_name
            assert result.items[i].trade_stats.total_trades == expected_trades

    def test_repository_data_integrity(self):
        """リポジトリデータの整合性テスト"""
        # 全てのアイテムが正しく設定されていることを確認
        all_items = self.repository.find_all()
        assert len(all_items) == 15

        # 各アイテムの基本プロパティを確認
        item_names = [item.item_name for item in all_items]
        expected_names = [
            "伝説の剣", "鉄の剣", "ドラゴンスケールアーマー", "ヒーリングポーション",
            "ミスリルのインゴット", "幸運の指輪", "呪いのアミュレット", "魔法のクリスタル",
            "神聖な聖杯", "革の鎧", "マナポーション", "エルフの弓", "石ころ",
            "雷神の槌", "未知の鉱石"
        ]

        for name in expected_names:
            assert name in item_names

        # 各アイテムのデータが正しいことを確認（サンプルとして1つ）
        legendary_sword = next(item for item in all_items if item.item_name == "伝説の剣")
        assert legendary_sword.item_type == "weapon"
        assert legendary_sword.item_rarity == "legendary"
        assert legendary_sword.current_market_price == 50000
        assert legendary_sword.total_trades == 150

    def test_get_item_market_info_impl_direct_success(self):
        """_get_item_market_info_impl - 正常系の直接テスト"""
        result = self.service._get_item_market_info_impl("伝説の剣")

        assert isinstance(result, ItemMarketDto)
        assert result.item_name == "伝説の剣"
        assert result.item_type == "weapon"
        assert result.item_rarity == "legendary"

    def test_get_item_market_info_impl_direct_item_not_found(self):
        """_get_item_market_info_impl - 存在しないアイテムの直接テスト"""
        with pytest.raises(TradeMarketQueryApplicationException) as exc_info:
            self.service._get_item_market_info_impl("存在しないアイテム")

        assert "Item market information not found: 存在しないアイテム" in str(exc_info.value)

    def test_get_popular_items_market_impl_direct_default_limit(self):
        """_get_popular_items_market_impl - デフォルトlimitの直接テスト"""
        result = self.service._get_popular_items_market_impl(10)

        assert isinstance(result, ItemMarketListDto)
        assert len(result.items) == 10
        assert result.total_count == 10

        # 取引量で降順にソートされていることを確認
        for i in range(len(result.items) - 1):
            assert result.items[i].trade_stats.total_trades >= result.items[i + 1].trade_stats.total_trades

    def test_get_popular_items_market_impl_direct_custom_limit(self):
        """_get_popular_items_market_impl - カスタムlimitの直接テスト"""
        result = self.service._get_popular_items_market_impl(5)

        assert len(result.items) == 5
        assert result.total_count == 5

    def test_get_popular_items_market_impl_direct_zero_limit(self):
        """_get_popular_items_market_impl - limit=0の直接テスト"""
        result = self.service._get_popular_items_market_impl(0)

        assert len(result.items) == 0
        assert result.total_count == 0

    def test_get_popular_items_market_impl_direct_large_limit(self):
        """_get_popular_items_market_impl - アイテム数以上のlimitの直接テスト"""
        result = self.service._get_popular_items_market_impl(20)

        assert len(result.items) == 15  # 全アイテム数
        assert result.total_count == 15

    def test_get_popular_items_market_negative_limit(self):
        """get_popular_items_market - 負のlimit値のテスト"""
        # 負の値が渡された場合、バリデーションエラーが発生する
        with pytest.raises(TradeMarketQueryApplicationException) as exc_info:
            self.service.get_popular_items_market(limit=-1)

        assert "Limit must be non-negative, got -1" in str(exc_info.value)
        assert exc_info.value.context["limit"] == -1

    def test_get_popular_items_market_very_large_limit(self):
        """get_popular_items_market - 非常に大きなlimit値のテスト"""
        result = self.service.get_popular_items_market(limit=1000)

        # アイテム数以上のlimitでも全件返される
        assert isinstance(result, ItemMarketListDto)
        assert len(result.items) == 15
        assert result.total_count == 15

    def test_get_item_market_info_empty_string(self):
        """get_item_market_info - 空文字列のアイテム名テスト"""
        with pytest.raises(TradeMarketQueryApplicationException) as exc_info:
            self.service.get_item_market_info("")

        assert "Item market information not found:" in str(exc_info.value)
        assert exc_info.value.context["item_name"] == ""

    def test_get_item_market_info_none_string(self):
        """get_item_market_info - None値のテスト"""
        with pytest.raises(TradeMarketQueryApplicationException) as exc_info:
            # Noneを渡すと存在しないアイテムとして扱われる
            self.service.get_item_market_info(None)

        assert "Item market information not found: None" in str(exc_info.value)

    @patch('src.application.trade.services.trade_market_query_service.logging.Logger.error')
    def test_execute_with_error_handling_logs_unexpected_error(self, mock_log):
        """_execute_with_error_handling - 予期しない例外時のログ出力テスト"""
        def failing_operation():
            raise ValueError("Unexpected error occurred")

        with pytest.raises(SystemErrorException) as exc_info:
            self.service._execute_with_error_handling(
                operation=failing_operation,
                context={"action": "test_action", "param": "test_value"}
            )

        # ログが正しく出力されたことを確認
        mock_log.assert_called_once_with(
            "Unexpected error in test_action: Unexpected error occurred",
            extra={'error_details': {"action": "test_action", "param": "test_value"}}
        )

        # 例外の内容を確認
        assert "test_action failed: Unexpected error occurred" in str(exc_info.value)
        assert isinstance(exc_info.value.original_exception, ValueError)

    @patch('src.application.trade.services.trade_market_query_service.logging.Logger.error')
    def test_execute_with_error_handling_logs_unexpected_error_empty_context(self, mock_log):
        """_execute_with_error_handling - 空コンテキストでの予期しない例外時のログ出力テスト"""
        def failing_operation():
            raise RuntimeError("Runtime error")

        with pytest.raises(SystemErrorException) as exc_info:
            self.service._execute_with_error_handling(
                operation=failing_operation,
                context={}
            )

        # ログが"unknown"として出力されたことを確認
        mock_log.assert_called_once_with(
            "Unexpected error in unknown: Runtime error",
            extra={'error_details': {}}
        )

        assert "unknown failed: Runtime error" in str(exc_info.value)
        assert isinstance(exc_info.value.original_exception, RuntimeError)

    @patch('src.application.trade.services.trade_market_query_service.logging.Logger.error')
    def test_execute_with_error_handling_no_log_for_application_exception(self, mock_log):
        """_execute_with_error_handling - TradeMarketQueryApplicationException時はログ出力されない"""
        def failing_operation():
            raise TradeMarketQueryApplicationException("Application error", app_param="value")

        with pytest.raises(TradeMarketQueryApplicationException):
            self.service._execute_with_error_handling(
                operation=failing_operation,
                context={"action": "test_action"}
            )

        # アプリケーション例外の場合はログ出力されない
        mock_log.assert_not_called()

    @patch('src.application.trade.services.trade_market_query_service.logging.Logger.error')
    def test_execute_with_error_handling_no_log_for_domain_exception(self, mock_log):
        """_execute_with_error_handling - DomainException時はログ出力されない"""
        class TestDomainException(DomainException):
            error_code = "TEST_ERROR"
            category = DomainException.category

        def failing_operation():
            raise TestDomainException("Domain error", domain_param="value")

        with pytest.raises(TradeMarketQueryApplicationException):
            self.service._execute_with_error_handling(
                operation=failing_operation,
                context={"action": "test_action"}
            )

        # ドメイン例外の場合はログ出力されない（アプリケーション例外に変換される）
        mock_log.assert_not_called()
