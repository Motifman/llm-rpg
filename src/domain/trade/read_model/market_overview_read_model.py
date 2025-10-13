from datetime import datetime, date
from typing import List
from dataclasses import dataclass


@dataclass
class MarketOverviewReadModel:
    """市場全体概要用ReadModel

    CQRSパターンのReadModelとして機能し、市場全体の統計情報を保持する。
    """

    # 集計データ
    total_active_listings: int
    total_completed_trades_today: int
    average_success_rate: float
    top_traded_items: List[str]
    last_updated: datetime

    # 集計基準日
    aggregated_date: date

    @classmethod
    def create_from_aggregated_data(
        cls,
        total_active_listings: int,
        total_completed_trades_today: int,
        average_success_rate: float,
        top_traded_items: List[str],
        last_updated: datetime,
        aggregated_date: date
    ) -> "MarketOverviewReadModel":
        """集計データからReadModelを作成"""
        return cls(
            total_active_listings=total_active_listings,
            total_completed_trades_today=total_completed_trades_today,
            average_success_rate=average_success_rate,
            top_traded_items=top_traded_items,
            last_updated=last_updated,
            aggregated_date=aggregated_date
        )

    @property
    def has_active_listings(self) -> bool:
        """アクティブな出品があるかどうか"""
        return self.total_active_listings > 0

    @property
    def has_completed_trades_today(self) -> bool:
        """今日の成立取引があるかどうか"""
        return self.total_completed_trades_today > 0
