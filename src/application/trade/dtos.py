from dataclasses import dataclass
from typing import List, Optional
from datetime import datetime
from src.domain.trade.trade_enum import TradeType, TradeStatus


@dataclass
class TradeItemDto:
    """取引アイテムDTO"""
    item_id: int
    count: Optional[int] = None
    unique_id: Optional[int] = None
    item_name: Optional[str] = None
    item_description: Optional[str] = None


@dataclass
class TradeOfferDto:
    """取引オファーDTO"""
    trade_id: int
    seller_id: int
    seller_name: str
    offered_item: TradeItemDto
    requested_gold: int
    trade_type: TradeType
    status: TradeStatus
    created_at: datetime
    target_player_id: Optional[int] = None
    target_player_name: Optional[str] = None
    buyer_id: Optional[int] = None
    buyer_name: Optional[str] = None
    completed_at: Optional[datetime] = None


@dataclass
class CreateTradeResultDto:
    """取引作成結果DTO"""
    success: bool
    message: str
    trade_id: Optional[int] = None
    error_message: Optional[str] = None


@dataclass
class ExecuteTradeResultDto:
    """取引実行結果DTO"""
    success: bool
    trade_id: int
    seller_id: int
    buyer_id: int
    offered_item: TradeItemDto
    requested_gold: int
    message: str
    error_message: Optional[str] = None


@dataclass
class CancelTradeResultDto:
    """取引キャンセル結果DTO"""
    success: bool
    trade_id: int
    player_id: int
    message: str
    error_message: Optional[str] = None


@dataclass
class PlayerTradesDto:
    """プレイヤーの取引一覧DTO"""
    player_id: int
    player_name: str
    active_trades: List[TradeOfferDto]
    completed_trades: List[TradeOfferDto]
    cancelled_trades: List[TradeOfferDto]
    total_trades: int


@dataclass
class GlobalTradesDto:
    """グローバル取引一覧DTO"""
    trades: List[TradeOfferDto]
    total_count: int
    filtered_count: int
    applied_filters: dict


@dataclass
class TradeFilterDto:
    """取引フィルターDTO"""
    item_id: Optional[int] = None
    item_name: Optional[str] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    trade_type: Optional[TradeType] = None
    status: Optional[TradeStatus] = None
    seller_id: Optional[int] = None
    buyer_id: Optional[int] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
