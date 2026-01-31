"""
InMemoryItemTradeStatisticsReadModelRepositoryのテスト
"""
import pytest
from datetime import datetime, timedelta

from src.infrastructure.repository.in_memory_item_trade_statistics_read_model_repository import InMemoryItemTradeStatisticsReadModelRepository
from src.domain.trade.read_model.item_trade_statistics_read_model import ItemTradeStatisticsReadModel
from src.domain.item.value_object.item_spec_id import ItemSpecId


class TestInMemoryItemTradeStatisticsReadModelRepository:
    """InMemoryItemTradeStatisticsReadModelRepositoryのテストクラス"""

    def setup_method(self):
        """各テストメソッド実行前に呼ばれる"""
        self.repository = InMemoryItemTradeStatisticsReadModelRepository()

    def test_find_by_id_existing_statistics(self):
        """存在する統計情報をIDで検索できる"""
        stats = self.repository.find_by_id(ItemSpecId(1))
        assert stats is not None
        assert stats.item_spec_id == ItemSpecId(1)
        assert stats.total_trades == 15
        assert stats.success_rate == 0.87

    def test_find_by_id_non_existing_statistics(self):
        """存在しない統計情報をIDで検索するとNoneが返る"""
        stats = self.repository.find_by_id(ItemSpecId(999))
        assert stats is None

    def test_find_by_ids_multiple_statistics(self):
        """複数の統計情報をIDリストで検索できる"""
        stats_ids = [ItemSpecId(1), ItemSpecId(2), ItemSpecId(999)]
        statistics = self.repository.find_by_ids(stats_ids)

        assert len(statistics) == 2
        assert statistics[0].item_spec_id == ItemSpecId(1)
        assert statistics[1].item_spec_id == ItemSpecId(2)

    def test_find_all_returns_all_statistics(self):
        """find_allですべての統計情報を取得できる"""
        all_statistics = self.repository.find_all()
        assert len(all_statistics) >= 8  # サンプルデータが8件以上あるはず

        # アイテムスペックIDがユニークであることを確認
        spec_ids = [stats.item_spec_id for stats in all_statistics]
        assert len(spec_ids) == len(set(spec_ids))

    def test_save_and_find_new_statistics(self):
        """新しい統計情報を保存して検索できる"""
        # 新しい統計情報を作成
        new_stats = ItemTradeStatisticsReadModel.create_from_statistics(
            item_spec_id=ItemSpecId(100),
            min_price=1000,
            max_price=2000,
            avg_price=1500.0,
            median_price=1500,
            total_trades=10,
            success_rate=0.8,
            last_updated=datetime.now()
        )

        # 保存
        saved_stats = self.repository.save(new_stats)

        # 検索して確認
        found_stats = self.repository.find_by_id(ItemSpecId(100))
        assert found_stats is not None
        assert found_stats.item_spec_id == ItemSpecId(100)
        assert found_stats.total_trades == 10
        assert found_stats.success_rate == 0.8

    def test_delete_existing_statistics(self):
        """存在する統計情報を削除できる"""
        # 削除前に存在することを確認
        stats_before = self.repository.find_by_id(ItemSpecId(1))
        assert stats_before is not None

        # 削除
        result = self.repository.delete(ItemSpecId(1))
        assert result is True

        # 削除後に存在しないことを確認
        stats_after = self.repository.find_by_id(ItemSpecId(1))
        assert stats_after is None

    def test_delete_non_existing_statistics(self):
        """存在しない統計情報を削除しようとするとFalseが返る"""
        result = self.repository.delete(ItemSpecId(999))
        assert result is False

    def test_find_statistics_existing_item(self):
        """find_statisticsで存在するアイテムの統計を取得できる"""
        stats = self.repository.find_statistics(ItemSpecId(1))
        assert stats is not None
        assert stats.item_spec_id == ItemSpecId(1)
        assert stats.min_price == 400
        assert stats.max_price == 600
        assert stats.total_trades == 15

    def test_find_statistics_non_existing_item(self):
        """find_statisticsで存在しないアイテムの統計を取得しようとするとNoneが返る"""
        stats = self.repository.find_statistics(ItemSpecId(999))
        assert stats is None

    def test_find_statistics_item_with_trade_history(self):
        """取引履歴のあるアイテムの統計情報を取得できる"""
        stats = self.repository.find_statistics(ItemSpecId(3))  # 回復薬
        assert stats is not None
        assert stats.has_trade_history is True
        assert stats.has_price_data is True
        assert stats.price_range == (120, 200)

    def test_find_statistics_item_without_trade_history(self):
        """取引履歴のないアイテムの統計情報を取得できる"""
        stats = self.repository.find_statistics(ItemSpecId(7))  # 伝説の剣
        assert stats is not None
        assert stats.has_trade_history is False
        assert stats.has_price_data is False
        assert stats.price_range is None
        assert stats.min_price is None
        assert stats.max_price is None

    def test_clear_removes_all_statistics(self):
        """clearですべての統計情報が削除される"""
        # 削除前に統計情報が存在することを確認
        assert self.repository.get_statistics_count() > 0

        # クリア
        self.repository.clear()

        # 削除後に統計情報が存在しないことを確認
        assert self.repository.get_statistics_count() == 0
        all_statistics = self.repository.find_all()
        assert len(all_statistics) == 0

    def test_get_statistics_count_returns_correct_count(self):
        """get_statistics_countで正しい統計情報数を取得できる"""
        count = self.repository.get_statistics_count()
        all_statistics = self.repository.find_all()
        assert count == len(all_statistics)

    def test_sample_data_has_items_with_trade_history(self):
        """サンプルデータに取引履歴のあるアイテムが含まれている"""
        all_statistics = self.repository.find_all()

        items_with_history = [stats for stats in all_statistics if stats.has_trade_history]
        assert len(items_with_history) > 0

        # 取引履歴のあるアイテムは価格データも持っているはず
        for stats in items_with_history:
            if stats.total_trades > 0:
                # 成功率が0-1の範囲であることを確認
                assert 0.0 <= stats.success_rate <= 1.0

    def test_sample_data_has_items_without_trade_history(self):
        """サンプルデータに取引履歴のないアイテムが含まれている"""
        all_statistics = self.repository.find_all()

        items_without_history = [stats for stats in all_statistics if not stats.has_trade_history]
        assert len(items_without_history) > 0

        # 取引履歴のないアイテムの確認
        for stats in items_without_history:
            assert stats.total_trades == 0
            assert stats.success_rate == 0.0

    def test_success_rate_percentage_calculation(self):
        """成功率のパーセント計算が正しく機能する"""
        all_statistics = self.repository.find_all()

        for stats in all_statistics:
            expected_percentage = stats.success_rate * 100.0
            assert stats.success_rate_percentage == expected_percentage

    def test_price_statistics_calculations(self):
        """価格統計の計算が正しく機能する"""
        # 価格データのある統計情報を取得
        stats_with_price = None
        for stats in self.repository.find_all():
            if stats.has_price_data:
                stats_with_price = stats
                break

        assert stats_with_price is not None

        # 価格範囲が正しいことを確認
        assert stats_with_price.price_range[0] == stats_with_price.min_price
        assert stats_with_price.price_range[1] == stats_with_price.max_price

        # 最小価格 <= 平均価格 <= 最大価格 の関係が成り立つことを確認
        assert stats_with_price.min_price <= stats_with_price.avg_price <= stats_with_price.max_price

    def test_statistics_with_none_prices(self):
        """価格データがNoneの統計情報の処理が正しい"""
        # 取引履歴のないアイテムを取得
        stats_without_price = None
        for stats in self.repository.find_all():
            if not stats.has_price_data:
                stats_without_price = stats
                break

        assert stats_without_price is not None

        # None値が正しく設定されていることを確認
        assert stats_without_price.min_price is None
        assert stats_without_price.max_price is None
        assert stats_without_price.avg_price is None
        assert stats_without_price.median_price is None
        assert stats_without_price.price_range is None

    def test_last_updated_timestamps(self):
        """最終更新日時の妥当性を確認"""
        all_statistics = self.repository.find_all()
        current_time = datetime.now()

        for stats in all_statistics:
            # 最終更新日時が現在時刻より過去であることを確認
            assert stats.last_updated <= current_time
            # 最終更新日時がNoneでないことを確認
            assert stats.last_updated is not None

    def test_statistics_data_integrity(self):
        """統計データの整合性を確認"""
        all_statistics = self.repository.find_all()

        for stats in all_statistics:
            # total_tradesは0以上であること
            assert stats.total_trades >= 0

            # success_rateは0.0-1.0の範囲であること
            assert 0.0 <= stats.success_rate <= 1.0

            # 価格データがある場合の整合性チェック
            if stats.has_price_data:
                assert stats.min_price >= 0
                assert stats.max_price >= 0
                assert stats.min_price <= stats.max_price
                assert stats.avg_price >= stats.min_price
                assert stats.avg_price <= stats.max_price
