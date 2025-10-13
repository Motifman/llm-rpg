"""
InMemoryMarketOverviewReadModelRepositoryのテスト
"""
import pytest
from datetime import datetime, date, timedelta
from typing import List

from src.infrastructure.repository.in_memory_market_overview_read_model_repository import InMemoryMarketOverviewReadModelRepository
from src.domain.trade.read_model.market_overview_read_model import MarketOverviewReadModel


class TestInMemoryMarketOverviewReadModelRepository:
    """InMemoryMarketOverviewReadModelRepositoryのテストクラス"""

    def setup_method(self):
        """各テストメソッド実行前に呼ばれる"""
        self.repository = InMemoryMarketOverviewReadModelRepository()

    def test_find_by_id_existing_overview(self):
        """存在する市場概要をID（日付）で検索できる"""
        today = date.today()
        overview = self.repository.find_by_id(today)

        assert overview is not None
        assert overview.aggregated_date == today
        assert isinstance(overview.total_active_listings, int)
        assert isinstance(overview.average_success_rate, float)

    def test_find_by_id_non_existing_overview(self):
        """存在しない市場概要をIDで検索するとNoneが返る"""
        future_date = date.today() + timedelta(days=365)
        overview = self.repository.find_by_id(future_date)
        assert overview is None

    def test_find_by_ids_multiple_overviews(self):
        """複数の市場概要をIDリストで検索できる"""
        today = date.today()
        yesterday = today - timedelta(days=1)
        future_date = today + timedelta(days=365)

        date_ids = [today, yesterday, future_date]
        overviews = self.repository.find_by_ids(date_ids)

        assert len(overviews) == 2  # todayとyesterdayのみ存在
        assert overviews[0].aggregated_date in [today, yesterday]
        assert overviews[1].aggregated_date in [today, yesterday]

    def test_find_all_returns_all_overviews(self):
        """find_allですべての市場概要を取得できる"""
        all_overviews = self.repository.find_all()
        assert len(all_overviews) >= 10  # サンプルデータが10件以上あるはず

        # 日付がユニークであることを確認
        dates = [overview.aggregated_date for overview in all_overviews]
        assert len(dates) == len(set(dates))

    def test_save_and_find_new_overview(self):
        """新しい市場概要を保存して検索できる"""
        # 新しい日付の市場概要を作成
        new_date = date.today() + timedelta(days=30)
        new_overview = MarketOverviewReadModel.create_from_aggregated_data(
            total_active_listings=100,
            total_completed_trades_today=30,
            average_success_rate=0.75,
            top_traded_items=["新アイテムA", "新アイテムB"],
            last_updated=datetime.now(),
            aggregated_date=new_date
        )

        # 保存
        saved_overview = self.repository.save(new_overview)

        # 検索して確認
        found_overview = self.repository.find_by_id(new_date)
        assert found_overview is not None
        assert found_overview.aggregated_date == new_date
        assert found_overview.total_active_listings == 100
        assert found_overview.total_completed_trades_today == 30
        assert found_overview.average_success_rate == 0.75
        assert "新アイテムA" in found_overview.top_traded_items

    def test_delete_existing_overview(self):
        """存在する市場概要を削除できる"""
        today = date.today()

        # 削除前に存在することを確認
        overview_before = self.repository.find_by_id(today)
        assert overview_before is not None

        # 削除
        result = self.repository.delete(today)
        assert result is True

        # 削除後に存在しないことを確認
        overview_after = self.repository.find_by_id(today)
        assert overview_after is None

    def test_delete_non_existing_overview(self):
        """存在しない市場概要を削除しようとするとFalseが返る"""
        future_date = date.today() + timedelta(days=365)
        result = self.repository.delete(future_date)
        assert result is False


    def test_find_latest_returns_most_recent_overview(self):
        """find_latestで最新の市場概要を取得できる"""
        latest_overview = self.repository.find_latest()
        assert latest_overview is not None

        # 全データを取得して最新日付を確認
        all_overviews = self.repository.find_all()
        max_date = max(overview.aggregated_date for overview in all_overviews)

        assert latest_overview.aggregated_date == max_date

    def test_find_latest_with_empty_repository(self):
        """空のリポジトリでfind_latestを呼び出すとNoneが返る"""
        # リポジトリをクリア
        self.repository.clear()

        latest_overview = self.repository.find_latest()
        assert latest_overview is None

    def test_clear_removes_all_overviews(self):
        """clearですべての市場概要が削除される"""
        # 削除前にデータが存在することを確認
        assert self.repository.count() > 0

        # クリア
        self.repository.clear()

        # 削除後にデータが存在しないことを確認
        assert self.repository.count() == 0
        all_overviews = self.repository.find_all()
        assert len(all_overviews) == 0

    def test_count_returns_correct_count(self):
        """countで正しいデータ数を取得できる"""
        count = self.repository.count()
        all_overviews = self.repository.find_all()
        assert count == len(all_overviews)

    def test_get_dates_with_data_returns_all_dates(self):
        """get_dates_with_dataでデータが存在する日付の一覧を取得できる"""
        dates = self.repository.get_dates_with_data()
        all_overviews = self.repository.find_all()
        expected_dates = [overview.aggregated_date for overview in all_overviews]

        assert set(dates) == set(expected_dates)
        # 日付がソートされていることを確認
        assert dates == sorted(dates)

    def test_get_overview_for_date_existing_date(self):
        """get_overview_for_dateで指定した日付の市場概要を取得できる"""
        today = date.today()
        overview = self.repository.get_overview_for_date(today)

        assert overview is not None
        assert overview.aggregated_date == today

    def test_get_overview_for_date_non_existing_date(self):
        """get_overview_for_dateで存在しない日付を指定するとNoneが返る"""
        future_date = date.today() + timedelta(days=365)
        overview = self.repository.get_overview_for_date(future_date)
        assert overview is None

    def test_has_data_for_date_existing_date(self):
        """has_data_for_dateでデータが存在する日付に対してTrueが返る"""
        today = date.today()
        assert self.repository.has_data_for_date(today) is True

    def test_has_data_for_date_non_existing_date(self):
        """has_data_for_dateでデータが存在しない日付に対してFalseが返る"""
        future_date = date.today() + timedelta(days=365)
        assert self.repository.has_data_for_date(future_date) is False

    def test_get_overviews_in_date_range(self):
        """get_overviews_in_date_rangeで指定した日付範囲内の市場概要を取得できる"""
        today = date.today()
        start_date = today - timedelta(days=3)
        end_date = today - timedelta(days=1)

        overviews = self.repository.get_overviews_in_date_range(start_date, end_date)

        # 全てのデータが範囲内であることを確認
        for overview in overviews:
            assert start_date <= overview.aggregated_date <= end_date

    def test_get_overviews_in_date_range_empty_range(self):
        """get_overviews_in_date_rangeでデータが存在しない範囲を指定すると空のリストが返る"""
        future_start = date.today() + timedelta(days=100)
        future_end = date.today() + timedelta(days=110)

        overviews = self.repository.get_overviews_in_date_range(future_start, future_end)
        assert len(overviews) == 0

    def test_get_overviews_with_active_listings_above(self):
        """get_overviews_with_active_listings_aboveでアクティブリスティング数が閾値以上のデータを取得できる"""
        threshold = 50
        overviews = self.repository.get_overviews_with_active_listings_above(threshold)

        # 全てのデータが閾値以上であることを確認
        for overview in overviews:
            assert overview.total_active_listings >= threshold

    def test_get_overviews_with_active_listings_above_high_threshold(self):
        """get_overviews_with_active_listings_aboveで高い閾値を指定すると該当するデータのみ取得できる"""
        threshold = 150  # サンプルデータでこれを超えるデータは少ないはず
        overviews = self.repository.get_overviews_with_active_listings_above(threshold)

        # 結果が少なくても、条件を満たすデータのみであることを確認
        for overview in overviews:
            assert overview.total_active_listings >= threshold

    def test_get_overviews_with_success_rate_above(self):
        """get_overviews_with_success_rate_aboveで成功率が閾値以上のデータを取得できる"""
        threshold = 0.8
        overviews = self.repository.get_overviews_with_success_rate_above(threshold)

        # 全てのデータが閾値以上であることを確認
        for overview in overviews:
            assert overview.average_success_rate >= threshold

    def test_get_overviews_with_success_rate_above_low_threshold(self):
        """get_overviews_with_success_rate_aboveで低い閾値を指定すると多くのデータが取得できる"""
        threshold = 0.1  # 低い閾値
        overviews = self.repository.get_overviews_with_success_rate_above(threshold)

        # 結果が多いことを確認（サンプルデータでほとんどが0.1以上のはず）
        assert len(overviews) > 5

        # 全てのデータが閾値以上であることを確認
        for overview in overviews:
            assert overview.average_success_rate >= threshold

    def test_sample_data_has_various_active_listings(self):
        """サンプルデータに様々なアクティブリスティング数が含まれている"""
        all_overviews = self.repository.find_all()

        active_listings_values = [overview.total_active_listings for overview in all_overviews]

        # 0件から200件以上の幅広い値が存在することを確認
        assert min(active_listings_values) == 0  # アクティブリスティングなしの日がある
        assert max(active_listings_values) >= 100  # 多くのアクティブリスティングの日がある

    def test_sample_data_has_various_completed_trades(self):
        """サンプルデータに様々な取引成立数が含まれている"""
        all_overviews = self.repository.find_all()

        completed_trades_values = [overview.total_completed_trades_today for overview in all_overviews]

        # 0件から150件以上の幅広い値が存在することを確認
        assert min(completed_trades_values) == 0  # 取引成立なしの日がある
        assert max(completed_trades_values) >= 50  # 多くの取引成立の日がある

    def test_sample_data_has_various_success_rates(self):
        """サンプルデータに様々な成功率が含まれている"""
        all_overviews = self.repository.find_all()

        success_rates = [overview.average_success_rate for overview in all_overviews]

        # 0.0から1.0の幅広い成功率が存在することを確認
        assert min(success_rates) == 0.0  # 成功率0%の日がある
        assert max(success_rates) == 1.0  # 成功率100%の日がある

        # 様々な成功率の値が存在することを確認
        unique_rates = set(success_rates)
        assert len(unique_rates) >= 5  # 少なくとも5種類の異なる成功率がある

    def test_sample_data_has_various_top_items(self):
        """サンプルデータに様々な人気アイテムが含まれている"""
        all_overviews = self.repository.find_all()

        all_top_items = []
        for overview in all_overviews:
            all_top_items.extend(overview.top_traded_items)

        unique_items = set(all_top_items)

        # 少なくとも10種類以上の異なるアイテムが存在することを確認
        assert len(unique_items) >= 10

        # 代表的なアイテムが存在することを確認
        item_names = list(unique_items)
        assert any("剣" in item for item in item_names)
        assert any("ポーション" in item for item in item_names)
        assert any("鎧" in item for item in item_names)

    def test_sample_data_has_recent_dates(self):
        """サンプルデータの日付が最近のものであることを確認"""
        all_overviews = self.repository.find_all()
        today = date.today()

        dates = [overview.aggregated_date for overview in all_overviews]

        # 全ての日付が今日から10日前以降であることを確認
        for overview_date in dates:
            assert overview_date >= today - timedelta(days=10)
            assert overview_date <= today

    def test_save_updates_existing_overview(self):
        """既存の市場概要を保存すると更新される"""
        today = date.today()

        # 元のデータを取得
        original_overview = self.repository.find_by_id(today)
        original_listings = original_overview.total_active_listings

        # 更新したデータを保存
        updated_overview = MarketOverviewReadModel.create_from_aggregated_data(
            total_active_listings=original_listings + 100,  # 値を変更
            total_completed_trades_today=original_overview.total_completed_trades_today,
            average_success_rate=original_overview.average_success_rate,
            top_traded_items=original_overview.top_traded_items,
            last_updated=datetime.now(),
            aggregated_date=today
        )

        self.repository.save(updated_overview)

        # 更新されたことを確認
        found_overview = self.repository.find_by_id(today)
        assert found_overview.total_active_listings == original_listings + 100

    def test_find_latest_after_save_new_overview(self):
        """新しい市場概要を保存した後にfind_latestが正しく動作する"""
        # 新しい日付（未来の日付）のデータを保存
        future_date = date.today() + timedelta(days=1)
        future_overview = MarketOverviewReadModel.create_from_aggregated_data(
            total_active_listings=200,
            total_completed_trades_today=100,
            average_success_rate=0.95,
            top_traded_items=["未来アイテム"],
            last_updated=datetime.now(),
            aggregated_date=future_date
        )

        self.repository.save(future_overview)

        # find_latestで新しいデータが返ることを確認
        latest_overview = self.repository.find_latest()
        assert latest_overview.aggregated_date == future_date
        assert latest_overview.total_active_listings == 200
