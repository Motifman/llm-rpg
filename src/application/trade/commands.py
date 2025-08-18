from dataclasses import dataclass
from typing import Optional
from src.domain.trade.trade_enum import TradeType


@dataclass(frozen=True)
class CreateTradeCommand:
    """取引作成コマンド"""
    seller_id: int
    requested_gold: int
    offered_item_id: int
    offered_item_count: Optional[int] = None
    offered_unique_id: Optional[int] = None
    trade_type: TradeType = TradeType.GLOBAL
    target_player_id: Optional[int] = None
    
    def __post_init__(self):
        """バリデーション"""
        if self.seller_id <= 0:
            raise ValueError("seller_id must be greater than 0")
        if self.requested_gold <= 0:
            raise ValueError("requested_gold must be greater than 0")
        if self.offered_item_id <= 0:
            raise ValueError("offered_item_id must be greater than 0")
        
        # スタック可能アイテムかユニークアイテムのどちらかである必要がある
        is_stackable = self.offered_item_count is not None
        is_unique = self.offered_unique_id is not None
        
        if not (is_stackable or is_unique):
            raise ValueError("Either offered_item_count or offered_unique_id must be provided")
        if is_stackable and is_unique:
            raise ValueError("Cannot provide both offered_item_count and offered_unique_id")
        if is_stackable and self.offered_item_count <= 0:
            raise ValueError("offered_item_count must be greater than 0")
        
        # 直接取引の場合は対象プレイヤーが必要
        if self.trade_type == TradeType.DIRECT and self.target_player_id is None:
            raise ValueError("target_player_id is required for DIRECT trade")
        if self.trade_type != TradeType.DIRECT and self.target_player_id is not None:
            raise ValueError("target_player_id must be None for GLOBAL trade")


@dataclass(frozen=True)
class ExecuteTradeCommand:
    """取引実行コマンド"""
    trade_id: int
    buyer_id: int
    
    def __post_init__(self):
        """バリデーション"""
        if self.trade_id <= 0:
            raise ValueError("trade_id must be greater than 0")
        if self.buyer_id <= 0:
            raise ValueError("buyer_id must be greater than 0")


@dataclass(frozen=True)
class CancelTradeCommand:
    """取引キャンセルコマンド"""
    trade_id: int
    player_id: int
    
    def __post_init__(self):
        """バリデーション"""
        if self.trade_id <= 0:
            raise ValueError("trade_id must be greater than 0")
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")


@dataclass(frozen=True)
class GetPlayerTradesCommand:
    """プレイヤーの取引取得コマンド"""
    player_id: int
    
    def __post_init__(self):
        """バリデーション"""
        if self.player_id <= 0:
            raise ValueError("player_id must be greater than 0")


@dataclass(frozen=True)
class GetGlobalTradesCommand:
    """グローバル取引取得コマンド"""
    item_id: Optional[int] = None
    min_price: Optional[int] = None
    max_price: Optional[int] = None
    limit: int = 10
    
    def __post_init__(self):
        """バリデーション"""
        if self.item_id is not None and self.item_id <= 0:
            raise ValueError("item_id must be greater than 0")
        if self.min_price is not None and self.min_price < 0:
            raise ValueError("min_price must be greater than or equal to 0")
        if self.max_price is not None and self.max_price < 0:
            raise ValueError("max_price must be greater than or equal to 0")
        if self.min_price is not None and self.max_price is not None and self.min_price > self.max_price:
            raise ValueError("min_price must be less than or equal to max_price")
        if self.limit <= 0:
            raise ValueError("limit must be greater than 0")
