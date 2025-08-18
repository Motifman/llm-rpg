from dataclasses import dataclass
from typing import Optional
from datetime import datetime
import uuid
from src.domain.trade.trade_enum import TradeType, TradeStatus


@dataclass(frozen=True)
class TradeCreatedEvent:
    """取引作成イベント"""
    trade_id: int
    seller_id: int
    seller_name: str
    offered_item_id: int
    offered_item_count: Optional[int]
    offered_unique_id: Optional[int]
    requested_gold: int
    trade_type: TradeType
    target_player_id: Optional[int] = None
    event_id: int = None
    occurred_at: datetime = None
    aggregate_id: int = None
    aggregate_type: str = None
    event_version: int = 1
    
    @classmethod
    def create(cls, trade_id: int, seller_id: int, seller_name: str, 
               offered_item_id: int, offered_item_count: Optional[int], 
               offered_unique_id: Optional[int], requested_gold: int, 
               trade_type: TradeType, target_player_id: Optional[int] = None):
        return cls(
            event_id=int(uuid.uuid4()),
            occurred_at=datetime.now(),
            aggregate_id=trade_id,
            aggregate_type="TradeOffer",
            event_version=1,
            trade_id=trade_id,
            seller_id=seller_id,
            seller_name=seller_name,
            offered_item_id=offered_item_id,
            offered_item_count=offered_item_count,
            offered_unique_id=offered_unique_id,
            requested_gold=requested_gold,
            trade_type=trade_type,
            target_player_id=target_player_id
        )


@dataclass(frozen=True)
class TradeExecutedEvent:
    """取引成立イベント"""
    trade_id: int
    seller_id: int
    seller_name: str
    buyer_id: int
    buyer_name: str
    offered_item_id: int
    offered_item_count: Optional[int]
    offered_unique_id: Optional[int]
    requested_gold: int
    trade_type: TradeType
    event_id: int = None
    occurred_at: datetime = None
    aggregate_id: int = None
    aggregate_type: str = None
    event_version: int = 1
    
    @classmethod
    def create(cls, trade_id: int, seller_id: int, seller_name: str, 
               buyer_id: int, buyer_name: str, offered_item_id: int, 
               offered_item_count: Optional[int], offered_unique_id: Optional[int], 
               requested_gold: int, trade_type: TradeType):
        return cls(
            event_id=int(uuid.uuid4()),
            occurred_at=datetime.now(),
            aggregate_id=trade_id,
            aggregate_type="TradeOffer",
            event_version=1,
            trade_id=trade_id,
            seller_id=seller_id,
            seller_name=seller_name,
            buyer_id=buyer_id,
            buyer_name=buyer_name,
            offered_item_id=offered_item_id,
            offered_item_count=offered_item_count,
            offered_unique_id=offered_unique_id,
            requested_gold=requested_gold,
            trade_type=trade_type
        )


@dataclass(frozen=True)
class TradeCancelledEvent:
    """取引キャンセルイベント"""
    trade_id: int
    seller_id: int
    seller_name: str
    offered_item_id: int
    offered_item_count: Optional[int]
    offered_unique_id: Optional[int]
    requested_gold: int
    trade_type: TradeType
    target_player_id: Optional[int] = None
    event_id: int = None
    occurred_at: datetime = None
    aggregate_id: int = None
    aggregate_type: str = None
    event_version: int = 1
    
    @classmethod
    def create(cls, trade_id: int, seller_id: int, seller_name: str, 
               offered_item_id: int, offered_item_count: Optional[int], 
               offered_unique_id: Optional[int], requested_gold: int, 
               trade_type: TradeType, target_player_id: Optional[int] = None):
        return cls(
            event_id=int(uuid.uuid4()),
            occurred_at=datetime.now(),
            aggregate_id=trade_id,
            aggregate_type="TradeOffer",
            event_version=1,
            trade_id=trade_id,
            seller_id=seller_id,
            seller_name=seller_name,
            offered_item_id=offered_item_id,
            offered_item_count=offered_item_count,
            offered_unique_id=offered_unique_id,
            requested_gold=requested_gold,
            trade_type=trade_type,
            target_player_id=target_player_id
        )


@dataclass(frozen=True)
class DirectTradeOfferedEvent:
    """直接取引提案イベント"""
    trade_id: int
    seller_id: int
    seller_name: str
    target_player_id: int
    target_player_name: str
    offered_item_id: int
    offered_item_count: Optional[int]
    offered_unique_id: Optional[int]
    requested_gold: int
    event_id: int = None
    occurred_at: datetime = None
    aggregate_id: int = None
    aggregate_type: str = None
    event_version: int = 1
    
    @classmethod
    def create(cls, trade_id: int, seller_id: int, seller_name: str, 
               target_player_id: int, target_player_name: str, offered_item_id: int, 
               offered_item_count: Optional[int], offered_unique_id: Optional[int], 
               requested_gold: int):
        return cls(
            event_id=int(uuid.uuid4()),
            occurred_at=datetime.now(),
            aggregate_id=trade_id,
            aggregate_type="TradeOffer",
            event_version=1,
            trade_id=trade_id,
            seller_id=seller_id,
            seller_name=seller_name,
            target_player_id=target_player_id,
            target_player_name=target_player_name,
            offered_item_id=offered_item_id,
            offered_item_count=offered_item_count,
            offered_unique_id=offered_unique_id,
            requested_gold=requested_gold
        )
