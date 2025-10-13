from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class TradeStatisticsDto:
    """取引統計DTO"""
    min_price: Optional[int]
    max_price: Optional[int]
    avg_price: Optional[float]
    median_price: Optional[int]
    total_trades: int
    success_rate: float
    last_updated: datetime


@dataclass(frozen=True)
class TradeDetailDto:
    """取引詳細DTO"""
    trade_id: int
    item_spec_id: int
    item_instance_id: int
    item_name: str
    item_quantity: int
    item_type: str
    item_rarity: str
    item_description: str
    item_equipment_type: Optional[str]
    durability_current: Optional[int]
    durability_max: Optional[int]
    requested_gold: int
    seller_name: str
    buyer_name: Optional[str]
    status: str
    statistics: TradeStatisticsDto
