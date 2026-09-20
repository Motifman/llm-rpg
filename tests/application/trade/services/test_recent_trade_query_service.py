"""
RecentTradeQueryServiceのテスト
"""
from unittest import mock

import pytest

from ai_rpg_world.application.common.exceptions import SystemErrorException
from ai_rpg_world.application.trade.contracts.recent_trade_dtos import RecentTradeDto, RecentTradeSummaryDto
from ai_rpg_world.application.trade.exceptions.recent_trade_query_application_exception import (
    RecentTradeQueryApplicationException,
)
from ai_rpg_world.application.trade.services.recent_trade_query_service import RecentTradeQueryService
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.infrastructure.repository.in_memory_recent_trade_read_model_repository import (
    InMemoryRecentTradeReadModelRepository,
)


class TestRecentTradeQueryService:
    """RecentTradeQueryServiceのテストクラス"""

    def setup_method(self):
        """各テストメソッド実行前に呼ばれる"""
        self.repository = InMemoryRecentTradeReadModelRepository()
        self.service = RecentTradeQueryService(self.repository)

    def test_constructor_initialization(self):
        """コンストラクタの初期化が正しく行われることを確認"""
        repository = InMemoryRecentTradeReadModelRepository()
        service = RecentTradeQueryService(repository)

        assert service._recent_trade_read_model_repository is repository
        assert service._logger is not None
        assert service._logger.name == "RecentTradeQueryService"

    def test_get_recent_trades_existing_item(self):
        """存在するアイテムの最近取引履歴を取得できる"""
        trade_dto = self.service.get_recent_trades("鋼の剣")

        assert isinstance(trade_dto, RecentTradeDto)
        assert trade_dto.item_name == "鋼の剣"
        assert isinstance(trade_dto.trades, list)
        assert len(trade_dto.trades) == 15  # 鋼の剣は15件の取引履歴がある

        # 取引履歴の構造を確認
        for trade in trade_dto.trades:
            assert isinstance(trade, RecentTradeSummaryDto)
            assert trade.item_name == "鋼の剣"
            assert isinstance(trade.trade_id, int)
            assert isinstance(trade.price, int)
            assert trade.price > 0  # 価格は正の数
            assert trade.traded_at is not None

        # 時系列順（新しい順）になっていることを確認
        for i in range(len(trade_dto.trades) - 1):
            assert trade_dto.trades[i].traded_at >= trade_dto.trades[i + 1].traded_at

    def test_get_recent_trades_another_existing_item(self):
        """別の存在するアイテムの最近取引履歴を取得できる"""
        trade_dto = self.service.get_recent_trades("魔法の杖")

        assert isinstance(trade_dto, RecentTradeDto)
        assert trade_dto.item_name == "魔法の杖"
        assert len(trade_dto.trades) == 8  # 魔法の杖は8件の取引履歴がある

        # 価格帯の確認（魔法の杖は高価なアイテム）
        for trade in trade_dto.trades:
            assert trade.price >= 800  # 魔法の杖のベース価格は1200なのでそれに近い

    def test_get_recent_trades_item_with_few_trades(self):
        """取引履歴が少ないアイテムの最近取引履歴を取得できる"""
        trade_dto = self.service.get_recent_trades("上級回復薬")

        assert isinstance(trade_dto, RecentTradeDto)
        assert trade_dto.item_name == "上級回復薬"
        assert len(trade_dto.trades) == 6  # 上級回復薬は6件の取引履歴がある

    def test_get_recent_trades_item_with_many_trades(self):
        """取引履歴が多いアイテムの最近取引履歴を取得できる"""
        trade_dto = self.service.get_recent_trades("回復薬")

        assert isinstance(trade_dto, RecentTradeDto)
        assert trade_dto.item_name == "回復薬"
        assert len(trade_dto.trades) == 25  # 回復薬は25件の取引履歴がある

    def test_get_recent_trades_item_with_no_trades(self):
        """取引履歴がないアイテムの最近取引履歴を取得できる"""
        trade_dto = self.service.get_recent_trades("伝説の剣")

        assert isinstance(trade_dto, RecentTradeDto)
        assert trade_dto.item_name == "伝説の剣"
        assert len(trade_dto.trades) == 0  # 伝説の剣は取引履歴がない

    def test_get_recent_trades_non_existing_item(self):
        """存在しないアイテム名を指定するとRecentTradeQueryApplicationExceptionが発生"""
        with pytest.raises(RecentTradeQueryApplicationException) as exc_info:
            self.service.get_recent_trades("存在しないアイテム")

        assert "Recent trades information not found: 存在しないアイテム" in str(exc_info.value)

    def test_get_recent_trades_empty_string_item_name(self):
        """空文字列のアイテム名を指定すると例外が発生"""
        with pytest.raises(RecentTradeQueryApplicationException) as exc_info:
            self.service.get_recent_trades("")

        assert "Recent trades information not found:" in str(exc_info.value)

    def test_get_recent_trades_none_item_name(self):
        """Noneのアイテム名を指定するとRecentTradeQueryApplicationExceptionが発生"""
        with pytest.raises(RecentTradeQueryApplicationException) as exc_info:
            self.service.get_recent_trades(None)

        assert "Recent trades information not found: None" in str(exc_info.value)

    def test_get_recent_trades_repository_returns_none(self):
        """リポジトリがNoneを返した場合の例外処理"""
        # モックを使用せずに、実際の動作をテストするため、
        # 直接リポジトリを操作して該当アイテムを削除
        original_find_by_item_name = self.repository.find_by_item_name

        def mock_find_by_item_name(item_name):
            if item_name == "テストアイテム":
                return None
            return original_find_by_item_name(item_name)

        self.repository.find_by_item_name = mock_find_by_item_name

        try:
            with pytest.raises(RecentTradeQueryApplicationException) as exc_info:
                self.service.get_recent_trades("テストアイテム")

            assert "Recent trades information not found: テストアイテム" in str(exc_info.value)
        finally:
            # モックを元に戻す
            self.repository.find_by_item_name = original_find_by_item_name

    def test_get_recent_trades_domain_exception_handling(self):
        """ドメイン例外が発生した場合の例外処理"""
        # モックを使用せずに、実際の動作をテストするため、
        # 直接リポジトリを操作してドメイン例外を発生させる
        original_find_by_item_name = self.repository.find_by_item_name

        class TestDomainException(DomainException):
            @property
            def error_code(self) -> str:
                return "TEST.DOMAIN_ERROR"

        def mock_find_by_item_name(item_name):
            if item_name == "ドメイン例外アイテム":
                raise TestDomainException("テストドメイン例外")
            return original_find_by_item_name(item_name)

        self.repository.find_by_item_name = mock_find_by_item_name

        try:
            with pytest.raises(RecentTradeQueryApplicationException) as exc_info:
                self.service.get_recent_trades("ドメイン例外アイテム")

            assert "Domain error in RecentTradeQuery usecase: TEST.DOMAIN_ERROR" in str(exc_info.value)
        finally:
            # モックを元に戻す
            self.repository.find_by_item_name = original_find_by_item_name

    def test_get_recent_trades_unexpected_exception_handling(self):
        """予期せぬ例外が発生した場合の例外処理"""
        # モックを使用せずに、実際の動作をテストするため、
        # 直接リポジトリを操作して予期せぬ例外を発生させる
        original_find_by_item_name = self.repository.find_by_item_name

        def mock_find_by_item_name(item_name):
            if item_name == "予期せぬ例外アイテム":
                raise ValueError("予期せぬテスト例外")
            return original_find_by_item_name(item_name)

        self.repository.find_by_item_name = mock_find_by_item_name

        try:
            with pytest.raises(SystemErrorException) as exc_info:
                self.service.get_recent_trades("予期せぬ例外アイテム")

            assert "failed: 予期せぬテスト例外" in str(exc_info.value)
        finally:
            # モックを元に戻す
            self.repository.find_by_item_name = original_find_by_item_name

    def test_get_recent_trades_logging_on_system_error(self, caplog):
        """システムエラー時のログ出力確認"""
        # モックを使用せずに、実際の動作をテストするため、
        # 直接リポジトリを操作して予期せぬ例外を発生させる
        original_find_by_item_name = self.repository.find_by_item_name

        def mock_find_by_item_name(item_name):
            if item_name == "ログテストアイテム":
                raise ValueError("ログテスト例外")
            return original_find_by_item_name(item_name)

        self.repository.find_by_item_name = mock_find_by_item_name

        try:
            with caplog.at_level('ERROR'):
                with pytest.raises(SystemErrorException):
                    self.service.get_recent_trades("ログテストアイテム")

                # ログ出力が記録されたことを確認
                assert len(caplog.records) == 1
                log_record = caplog.records[0]
                assert log_record.levelname == 'ERROR'
                assert log_record.name == 'RecentTradeQueryService'
                assert "Unexpected error in get_recent_trades: ログテスト例外" in log_record.message
        finally:
            # モックを元に戻す
            self.repository.find_by_item_name = original_find_by_item_name

    def test_get_recent_trades_price_validation(self):
        """取引価格が正の整数であることを確認"""
        trade_dto = self.service.get_recent_trades("鋼の剣")

        for trade in trade_dto.trades:
            assert isinstance(trade.price, int)
            assert trade.price > 0
            assert trade.price < 10000  # 現実的な価格帯

    def test_get_recent_trades_trade_id_uniqueness(self):
        """取引IDが一意であることを確認"""
        trade_dto = self.service.get_recent_trades("鋼の剣")

        trade_ids = [trade.trade_id for trade in trade_dto.trades]
        assert len(trade_ids) == len(set(trade_ids))  # 重複がないことを確認

    def test_get_recent_trades_timestamp_ordering(self):
        """取引時刻が新しい順に並んでいることを確認"""
        trade_dto = self.service.get_recent_trades("鋼の剣")

        for i in range(len(trade_dto.trades) - 1):
            assert trade_dto.trades[i].traded_at >= trade_dto.trades[i + 1].traded_at

    def test_get_recent_trades_all_sample_items(self):
        """全てのサンプルアイテムについて取引履歴を取得できることを確認"""
        sample_items = [
            "鋼の剣", "魔法の杖", "回復薬", "上級回復薬", "輝く宝石",
            "鉄の盾", "冒険者のブーツ", "魔法の書", "丈夫な縄", "伝説の剣"
        ]

        for item_name in sample_items:
            trade_dto = self.service.get_recent_trades(item_name)
            assert isinstance(trade_dto, RecentTradeDto)
            assert trade_dto.item_name == item_name
            assert isinstance(trade_dto.trades, list)

    def test_get_recent_trades_item_name_consistency(self):
        """DTO内のアイテム名がリクエストしたアイテム名と一致することを確認"""
        test_items = ["鋼の剣", "魔法の杖", "回復薬"]

        for item_name in test_items:
            trade_dto = self.service.get_recent_trades(item_name)
            assert trade_dto.item_name == item_name

            # 各取引サマリーのアイテム名も一致することを確認
            for trade in trade_dto.trades:
                assert trade.item_name == item_name

    def test_get_recent_trades_large_number_of_trades(self):
        """大量の取引履歴を持つアイテムの処理を確認"""
        # 25件の取引履歴を持つ回復薬でテスト
        trade_dto = self.service.get_recent_trades("回復薬")

        assert len(trade_dto.trades) == 25

        # 全ての取引が正しい構造を持っていることを確認
        for trade in trade_dto.trades:
            assert isinstance(trade.trade_id, int)
            assert isinstance(trade.price, int)
            assert trade.price > 0
            assert trade.traded_at is not None
            assert trade.item_name == "回復薬"

    def test_get_recent_trades_with_very_long_item_name(self):
        """非常に長いアイテム名での処理を確認"""
        long_item_name = "非常に長いアイテム名でテストを行うためのダミーアイテム名" * 10  # 約500文字

        with pytest.raises(RecentTradeQueryApplicationException) as exc_info:
            self.service.get_recent_trades(long_item_name)

        assert "Recent trades information not found:" in str(exc_info.value)

    def test_get_recent_trades_with_special_characters(self):
        """特殊文字を含むアイテム名での処理を確認"""
        special_item_names = [
            "アイテム@#$%^&*()",
            "アイテム\n\t\r",
            "アイテム'\"\\",
            "アイテム<>\"'",
            "アイテム日本語漢字",
            "アイテム🌟⭐🔥"
        ]

        for item_name in special_item_names:
            with pytest.raises(RecentTradeQueryApplicationException) as exc_info:
                self.service.get_recent_trades(item_name)

            assert "Recent trades information not found:" in str(exc_info.value)
