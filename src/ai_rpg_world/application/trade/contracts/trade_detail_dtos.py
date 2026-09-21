from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class TradeStatisticsDto:
    """取引統計DTO"""
    min_price: int | None
    max_price: int | None
    avg_price: float | None
    median_price: int | None
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
    item_equipment_type: str | None
    durability_current: int | None
    durability_max: int | None
    requested_gold: int
    seller_name: str
    buyer_name: str | None
    status: str
    statistics: TradeStatisticsDto
