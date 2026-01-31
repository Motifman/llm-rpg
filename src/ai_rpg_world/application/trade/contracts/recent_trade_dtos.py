from dataclasses import dataclass
from datetime import datetime
from typing import List


@dataclass(frozen=True)
class RecentTradeSummaryDto:
    """最近の取引サマリーDTO"""
    trade_id: int
    item_name: str
    price: int
    traded_at: datetime


@dataclass(frozen=True)
class RecentTradeDto:
    """最近の取引履歴DTO"""
    item_name: str
    trades: List[RecentTradeSummaryDto]
