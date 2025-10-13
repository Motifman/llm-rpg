from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MarketOverviewDto:
    """市場全体概要DTO"""
    total_active_listings: int
    total_completed_trades_today: int
    average_success_rate: float
    top_traded_items: list[str]
    last_updated: datetime
