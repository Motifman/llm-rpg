"""
MarketOverviewQueryServiceのテスト
"""
import pytest
from datetime import datetime, date, timedelta
from typing import Optional

from src.application.trade.services.market_overview_query_service import MarketOverviewQueryService
from src.infrastructure.repository.in_memory_market_overview_read_model_repository import InMemoryMarketOverviewReadModelRepository
from src.application.trade.contracts.market_overview_dtos import MarketOverviewDto
from src.application.trade.exceptions.market_overview_query_application_exception import MarketOverviewQueryApplicationException
from src.application.common.exceptions import SystemErrorException
from src.domain.common.exception import DomainException
from src.domain.trade.read_model.market_overview_read_model import MarketOverviewReadModel


class TestMarketOverviewQueryService:
    """MarketOverviewQueryServiceのテストクラス"""

    def setup_method(self):
        """各テストメソッド実行前に呼ばれる"""
        self.repository = InMemoryMarketOverviewReadModelRepository()
        self.service = MarketOverviewQueryService(self.repository)

    def test_get_market_overview_with_data(self):
        """データが存在する場合に市場概要を取得できる"""
        # 実行
        result = self.service.get_market_overview()

        # 検証
        assert isinstance(result, MarketOverviewDto)

        # リポジトリから最新データを取得して比較
        latest_read_model = self.repository.find_latest()
        assert latest_read_model is not None

        # DTOの内容がReadModelと一致することを確認
        assert result.total_active_listings == latest_read_model.total_active_listings
        assert result.total_completed_trades_today == latest_read_model.total_completed_trades_today
        assert result.average_success_rate == latest_read_model.average_success_rate
        assert result.top_traded_items == latest_read_model.top_traded_items
        assert result.last_updated == latest_read_model.last_updated

    def test_get_market_overview_no_data(self):
        """データが存在しない場合にMarketOverviewQueryApplicationExceptionが発生"""
        # データをクリア
        self.repository.clear()

        # 実行・検証
        with pytest.raises(MarketOverviewQueryApplicationException) as exc_info:
            self.service.get_market_overview()

        assert "Market overview information not found" in str(exc_info.value)

    def test_convert_to_dto(self):
        """ReadModelからDTOへの変換が正しく行われる"""
        # テスト用のReadModelを作成
        test_datetime = datetime(2024, 10, 12, 10, 30, 0)
        test_date = date(2024, 10, 12)

        read_model = MarketOverviewReadModel.create_from_aggregated_data(
            total_active_listings=100,
            total_completed_trades_today=25,
            average_success_rate=0.85,
            top_traded_items=["魔法の剣", "回復ポーション", "鉄の鎧"],
            last_updated=test_datetime,
            aggregated_date=test_date
        )

        # 変換実行
        result_dto = self.service._convert_to_dto(read_model)

        # 検証
        assert isinstance(result_dto, MarketOverviewDto)
        assert result_dto.total_active_listings == 100
        assert result_dto.total_completed_trades_today == 25
        assert result_dto.average_success_rate == 0.85
        assert result_dto.top_traded_items == ["魔法の剣", "回復ポーション", "鉄の鎧"]
        assert result_dto.last_updated == test_datetime

    def test_convert_to_dto_with_empty_listings(self):
        """アクティブリスティングが0件の場合の変換テスト"""
        test_datetime = datetime(2024, 10, 12, 10, 30, 0)
        test_date = date(2024, 10, 12)

        read_model = MarketOverviewReadModel.create_from_aggregated_data(
            total_active_listings=0,
            total_completed_trades_today=0,
            average_success_rate=0.0,
            top_traded_items=[],
            last_updated=test_datetime,
            aggregated_date=test_date
        )

        result_dto = self.service._convert_to_dto(read_model)

        assert result_dto.total_active_listings == 0
        assert result_dto.total_completed_trades_today == 0
        assert result_dto.average_success_rate == 0.0
        assert result_dto.top_traded_items == []

    def test_convert_to_dto_with_many_items(self):
        """多くのトップトレードアイテムがある場合の変換テスト"""
        test_datetime = datetime(2024, 10, 12, 10, 30, 0)
        test_date = date(2024, 10, 12)

        top_items = [
            "魔法の剣", "回復ポーション", "ドラゴンの鱗", "魔法の書", "鉄の鎧",
            "弓矢", "魔法の杖", "金の指輪", "銀のネックレス", "魔法の宝石"
        ]

        read_model = MarketOverviewReadModel.create_from_aggregated_data(
            total_active_listings=200,
            total_completed_trades_today=150,
            average_success_rate=1.0,
            top_traded_items=top_items,
            last_updated=test_datetime,
            aggregated_date=test_date
        )

        result_dto = self.service._convert_to_dto(read_model)

        assert result_dto.total_active_listings == 200
        assert result_dto.total_completed_trades_today == 150
        assert result_dto.average_success_rate == 1.0
        assert result_dto.top_traded_items == top_items

    def test_execute_with_error_handling_application_exception(self):
        """MarketOverviewQueryApplicationExceptionが発生した場合、そのまま再スローされる"""
        def operation_that_raises_app_exception():
            raise MarketOverviewQueryApplicationException("Test application exception")

        context = {"action": "test_action"}

        with pytest.raises(MarketOverviewQueryApplicationException) as exc_info:
            self.service._execute_with_error_handling(operation_that_raises_app_exception, context)

        assert "Test application exception" in str(exc_info.value)

    def test_execute_with_error_handling_domain_exception(self):
        """DomainExceptionが発生した場合、MarketOverviewQueryApplicationExceptionに変換される"""
        class TestDomainException(DomainException):
            error_code = "TEST_ERROR"

        def operation_that_raises_domain_exception():
            raise TestDomainException("Test domain error")

        context = {"action": "test_action"}

        with pytest.raises(MarketOverviewQueryApplicationException) as exc_info:
            self.service._execute_with_error_handling(operation_that_raises_domain_exception, context)

        assert "Domain error in MarketOverviewQuery usecase: TEST_ERROR" in str(exc_info.value)

    def test_execute_with_error_handling_unexpected_exception(self):
        """予期しない例外が発生した場合、SystemErrorExceptionに変換される"""
        def operation_that_raises_unexpected_exception():
            raise ValueError("Unexpected test error")

        context = {"action": "test_action"}

        with pytest.raises(SystemErrorException) as exc_info:
            self.service._execute_with_error_handling(operation_that_raises_unexpected_exception, context)

        assert "test_action failed: Unexpected test error" in str(exc_info.value)
        assert exc_info.value.original_exception is not None
        assert isinstance(exc_info.value.original_exception, ValueError)

    def test_execute_with_error_handling_success(self):
        """正常に実行された場合、結果が返される"""
        def operation_that_succeeds():
            return "success_result"

        context = {"action": "test_action"}

        result = self.service._execute_with_error_handling(operation_that_succeeds, context)

        assert result == "success_result"

    def test_get_market_overview_repository_failure(self):
        """リポジトリで予期しないエラーが発生した場合のテスト"""
        # モックリポジトリを作成して例外を発生させる
        class FailingRepository(InMemoryMarketOverviewReadModelRepository):
            def find_latest(self):
                raise RuntimeError("Database connection failed")

        failing_service = MarketOverviewQueryService(FailingRepository())

        with pytest.raises(SystemErrorException) as exc_info:
            failing_service.get_market_overview()

        assert "get_market_overview failed: Database connection failed" in str(exc_info.value)
        assert isinstance(exc_info.value.original_exception, RuntimeError)

    def test_convert_to_dto_boundary_values(self):
        """境界値を含む変換テスト"""
        test_datetime = datetime(2024, 10, 12, 10, 30, 0)
        test_date = date(2024, 10, 12)

        # 最小値のテスト
        min_read_model = MarketOverviewReadModel.create_from_aggregated_data(
            total_active_listings=0,
            total_completed_trades_today=0,
            average_success_rate=0.0,
            top_traded_items=[],
            last_updated=test_datetime,
            aggregated_date=test_date
        )

        min_dto = self.service._convert_to_dto(min_read_model)
        assert min_dto.total_active_listings == 0
        assert min_dto.average_success_rate == 0.0

        # 最大値のテスト（現実的な範囲で）
        max_read_model = MarketOverviewReadModel.create_from_aggregated_data(
            total_active_listings=10000,
            total_completed_trades_today=5000,
            average_success_rate=1.0,
            top_traded_items=["item"] * 100,  # 多数のアイテム
            last_updated=test_datetime,
            aggregated_date=test_date
        )

        max_dto = self.service._convert_to_dto(max_read_model)
        assert max_dto.total_active_listings == 10000
        assert max_dto.average_success_rate == 1.0
        assert len(max_dto.top_traded_items) == 100

    def test_convert_to_dto_special_characters(self):
        """特殊文字を含むアイテム名の変換テスト"""
        test_datetime = datetime(2024, 10, 12, 10, 30, 0)
        test_date = date(2024, 10, 12)

        special_items = [
            "魔法の剣★",
            "回復ポーション（高級）",
            "ドラゴンの鱗 - 希少",
            "魔法の書#スペシャル",
            "鉄の鎧@強化版"
        ]

        read_model = MarketOverviewReadModel.create_from_aggregated_data(
            total_active_listings=50,
            total_completed_trades_today=20,
            average_success_rate=0.75,
            top_traded_items=special_items,
            last_updated=test_datetime,
            aggregated_date=test_date
        )

        result_dto = self.service._convert_to_dto(read_model)

        assert result_dto.top_traded_items == special_items

    def test_error_handling_context_logging(self):
        """エラーハンドリング時のコンテキスト情報が正しく渡されるかのテスト"""
        # これは実際のログ出力をテストするのが難しいので、
        # エラーハンドリングが正しく動作することを確認する間接的なテスト
        def operation_that_raises_exception():
            raise ValueError("Test error for context")

        context = {"action": "test_operation", "user_id": 123, "request_id": "req-456"}

        with pytest.raises(SystemErrorException) as exc_info:
            self.service._execute_with_error_handling(operation_that_raises_exception, context)

        # SystemErrorExceptionが正しく生成されていることを確認
        assert exc_info.value.original_exception is not None
        assert isinstance(exc_info.value.original_exception, ValueError)
        assert "Test error for context" in str(exc_info.value.original_exception)


    def test_get_market_overview_multiple_calls_consistency(self):
        """複数回の呼び出しで一貫した結果が返される"""
        # 最初の呼び出し
        result1 = self.service.get_market_overview()

        # 2回目の呼び出し
        result2 = self.service.get_market_overview()

        # 結果が一致することを確認
        assert result1.total_active_listings == result2.total_active_listings
        assert result1.total_completed_trades_today == result2.total_completed_trades_today
        assert result1.average_success_rate == result2.average_success_rate
        assert result1.top_traded_items == result2.top_traded_items
        assert result1.last_updated == result2.last_updated
