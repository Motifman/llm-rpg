from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass(frozen=True)
class PriceStatisticsDto:
    """価格統計DTO"""
    current_market_price: int
    min_price: int
    max_price: int
    avg_price: float
    median_price: int


@dataclass(frozen=True)
class TradeStatisticsDto:
    """取引統計DTO"""
    total_trades: int
    active_listings: int
    completed_trades: int
    success_rate: float
    last_updated: datetime


@dataclass(frozen=True)
class ItemMarketDto:
    """アイテム市場情報DTO"""
    item_spec_id: int
    item_name: str
    item_type: str
    item_rarity: str

    price_stats: PriceStatisticsDto
    trade_stats: TradeStatisticsDto


@dataclass(frozen=True)
class ItemMarketListDto:
    """アイテム市場情報一覧DTO"""
    items: List[ItemMarketDto]
    total_count: int
