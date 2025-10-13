"""
InMemoryMarketOverviewReadModelRepository - MarketOverviewReadModelを使用するインメモリ実装
"""
from typing import List, Optional, Dict
from datetime import datetime, date, timedelta

from src.domain.trade.repository.market_overview_read_model_repository import MarketOverviewReadModelRepository
from src.domain.trade.read_model.market_overview_read_model import MarketOverviewReadModel


class InMemoryMarketOverviewReadModelRepository(MarketOverviewReadModelRepository):
    """MarketOverviewReadModelを使用するインメモリリポジトリ"""

    def __init__(self):
        self._overviews: Dict[date, MarketOverviewReadModel] = {}

        # サンプルデータを作成
        self._setup_sample_data()

    def _setup_sample_data(self):
        """サンプル市場概要データのセットアップ"""
        # 現在の日時を基準に過去のデータを生成
        base_datetime = datetime.now()
        base_date = base_datetime.date()

        # 今日の市場概要（最新データ）
        today_overview = MarketOverviewReadModel.create_from_aggregated_data(
            total_active_listings=75,
            total_completed_trades_today=25,
            average_success_rate=0.85,
            top_traded_items=["魔法の剣", "回復ポーション", "ドラゴンの鱗", "魔法の書", "鉄の鎧"],
            last_updated=base_datetime,
            aggregated_date=base_date
        )
        self._overviews[base_date] = today_overview

        # 昨日の市場概要（アクティブリスティングが多い日）
        yesterday = base_date - timedelta(days=1)
        yesterday_overview = MarketOverviewReadModel.create_from_aggregated_data(
            total_active_listings=120,
            total_completed_trades_today=45,
            average_success_rate=0.78,
            top_traded_items=["鉄の鎧", "魔法の剣", "回復ポーション", "弓矢", "魔法の杖"],
            last_updated=base_datetime - timedelta(days=1),
            aggregated_date=yesterday
        )
        self._overviews[yesterday] = yesterday_overview

        # 一昨日の市場概要（取引成立が多い日）
        day_before_yesterday = base_date - timedelta(days=2)
        day_before_yesterday_overview = MarketOverviewReadModel.create_from_aggregated_data(
            total_active_listings=60,
            total_completed_trades_today=55,
            average_success_rate=0.92,
            top_traded_items=["回復ポーション", "魔法の書", "ドラゴンの鱗", "鉄の鎧", "魔法の剣"],
            last_updated=base_datetime - timedelta(days=2),
            aggregated_date=day_before_yesterday
        )
        self._overviews[day_before_yesterday] = day_before_yesterday_overview

        # 3日前の市場概要（成功率が高い日）
        three_days_ago = base_date - timedelta(days=3)
        three_days_ago_overview = MarketOverviewReadModel.create_from_aggregated_data(
            total_active_listings=40,
            total_completed_trades_today=35,
            average_success_rate=0.95,
            top_traded_items=["魔法の書", "ドラゴンの鱗", "魔法の剣", "回復ポーション", "鉄の鎧"],
            last_updated=base_datetime - timedelta(days=3),
            aggregated_date=three_days_ago
        )
        self._overviews[three_days_ago] = three_days_ago_overview

        # 4日前の市場概要（アクティブリスティングが少ない日）
        four_days_ago = base_date - timedelta(days=4)
        four_days_ago_overview = MarketOverviewReadModel.create_from_aggregated_data(
            total_active_listings=15,
            total_completed_trades_today=8,
            average_success_rate=0.60,
            top_traded_items=["回復ポーション", "鉄の鎧", "弓矢", "魔法の剣", "魔法の杖"],
            last_updated=base_datetime - timedelta(days=4),
            aggregated_date=four_days_ago
        )
        self._overviews[four_days_ago] = four_days_ago_overview

        # 5日前の市場概要（取引成立が少ない日）
        five_days_ago = base_date - timedelta(days=5)
        five_days_ago_overview = MarketOverviewReadModel.create_from_aggregated_data(
            total_active_listings=85,
            total_completed_trades_today=5,
            average_success_rate=0.45,
            top_traded_items=["弓矢", "魔法の杖", "鉄の鎧", "回復ポーション", "魔法の剣"],
            last_updated=base_datetime - timedelta(days=5),
            aggregated_date=five_days_ago
        )
        self._overviews[five_days_ago] = five_days_ago_overview

        # 6日前の市場概要（成功率が低い日）
        six_days_ago = base_date - timedelta(days=6)
        six_days_ago_overview = MarketOverviewReadModel.create_from_aggregated_data(
            total_active_listings=90,
            total_completed_trades_today=20,
            average_success_rate=0.25,
            top_traded_items=["魔法の杖", "弓矢", "魔法の剣", "鉄の鎧", "回復ポーション"],
            last_updated=base_datetime - timedelta(days=6),
            aggregated_date=six_days_ago
        )
        self._overviews[six_days_ago] = six_days_ago_overview

        # 7日前の市場概要（アクティブリスティングなしの日）
        seven_days_ago = base_date - timedelta(days=7)
        seven_days_ago_overview = MarketOverviewReadModel.create_from_aggregated_data(
            total_active_listings=0,
            total_completed_trades_today=0,
            average_success_rate=0.0,
            top_traded_items=[],
            last_updated=base_datetime - timedelta(days=7),
            aggregated_date=seven_days_ago
        )
        self._overviews[seven_days_ago] = seven_days_ago_overview

        # 8日前の市場概要（全てのアイテムがトレードされた日）
        eight_days_ago = base_date - timedelta(days=8)
        eight_days_ago_overview = MarketOverviewReadModel.create_from_aggregated_data(
            total_active_listings=200,
            total_completed_trades_today=150,
            average_success_rate=1.0,
            top_traded_items=["魔法の剣", "回復ポーション", "ドラゴンの鱗", "魔法の書", "鉄の鎧", "弓矢", "魔法の杖", "金の指輪", "銀のネックレス", "魔法の宝石"],
            last_updated=base_datetime - timedelta(days=8),
            aggregated_date=eight_days_ago
        )
        self._overviews[eight_days_ago] = eight_days_ago_overview

        # 9日前の市場概要（レアアイテムが人気の日）
        nine_days_ago = base_date - timedelta(days=9)
        nine_days_ago_overview = MarketOverviewReadModel.create_from_aggregated_data(
            total_active_listings=110,
            total_completed_trades_today=40,
            average_success_rate=0.88,
            top_traded_items=["ドラゴンの鱗", "魔法の宝石", "金の指輪", "魔法の書", "銀のネックレス"],
            last_updated=base_datetime - timedelta(days=9),
            aggregated_date=nine_days_ago
        )
        self._overviews[nine_days_ago] = nine_days_ago_overview

        # 10日前の市場概要（通常的な日）
        ten_days_ago = base_date - timedelta(days=10)
        ten_days_ago_overview = MarketOverviewReadModel.create_from_aggregated_data(
            total_active_listings=65,
            total_completed_trades_today=22,
            average_success_rate=0.70,
            top_traded_items=["鉄の鎧", "魔法の剣", "回復ポーション", "弓矢", "魔法の杖"],
            last_updated=base_datetime - timedelta(days=10),
            aggregated_date=ten_days_ago
        )
        self._overviews[ten_days_ago] = ten_days_ago_overview

    def find_latest(self) -> Optional[MarketOverviewReadModel]:
        """最新の市場概要を取得

        Returns:
            最新の市場概要データ（存在しない場合はNone）
        """
        if not self._overviews:
            return None

        # aggregated_dateで降順ソートして最新を取得
        latest_date = max(self._overviews.keys())
        return self._overviews[latest_date]

    def find_by_id(self, entity_id: date) -> Optional[MarketOverviewReadModel]:
        """ID（集計日）で市場概要を検索"""
        return self._overviews.get(entity_id)

    def find_by_ids(self, entity_ids: List[date]) -> List[MarketOverviewReadModel]:
        """複数の集計日で市場概要を検索"""
        result = []
        for entity_id in entity_ids:
            overview = self._overviews.get(entity_id)
            if overview:
                result.append(overview)
        return result

    def save(self, entity: MarketOverviewReadModel) -> MarketOverviewReadModel:
        """市場概要を保存"""
        self._overviews[entity.aggregated_date] = entity
        return entity

    def delete(self, entity_id: date) -> bool:
        """市場概要を削除"""
        if entity_id in self._overviews:
            del self._overviews[entity_id]
            return True
        return False

    def find_all(self) -> List[MarketOverviewReadModel]:
        """全ての市場概要を取得"""
        return list(self._overviews.values())

    # テスト用のヘルパーメソッド
    def clear(self) -> None:
        """全ての市場概要データを削除（テスト用）"""
        self._overviews.clear()

    def count(self) -> int:
        """市場概要データの総数を取得"""
        return len(self._overviews)

    def get_dates_with_data(self) -> List[date]:
        """データが存在する日付の一覧を取得"""
        return sorted(self._overviews.keys())

    def get_overview_for_date(self, target_date: date) -> Optional[MarketOverviewReadModel]:
        """指定した日付の市場概要を取得"""
        return self._overviews.get(target_date)

    def has_data_for_date(self, target_date: date) -> bool:
        """指定した日付のデータが存在するかチェック"""
        return target_date in self._overviews

    def get_overviews_in_date_range(self, start_date: date, end_date: date) -> List[MarketOverviewReadModel]:
        """指定した日付範囲内の市場概要を取得"""
        result = []
        current_date = start_date
        while current_date <= end_date:
            overview = self._overviews.get(current_date)
            if overview:
                result.append(overview)
            current_date += timedelta(days=1)
        return result

    def get_overviews_with_active_listings_above(self, threshold: int) -> List[MarketOverviewReadModel]:
        """アクティブリスティング数が指定値以上の市場概要を取得"""
        return [overview for overview in self._overviews.values() if overview.total_active_listings >= threshold]

    def get_overviews_with_success_rate_above(self, threshold: float) -> List[MarketOverviewReadModel]:
        """成功率が指定値以上の市場概要を取得"""
        return [overview for overview in self._overviews.values() if overview.average_success_rate >= threshold]
