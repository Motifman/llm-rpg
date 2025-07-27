from dataclasses import dataclass, field
from typing import Optional
import uuid
from datetime import datetime
from game.enums import TradeType, TradeStatus


@dataclass(frozen=True)
class TradeOffer:
    """取引オファー"""
    trade_id: str
    seller_id: str
    offered_item_id: str
    offered_item_count: int
    requested_money: int
    requested_item_id: Optional[str] = None
    requested_item_count: int = 1
    trade_type: TradeType = TradeType.GLOBAL
    target_player_id: Optional[str] = None  # 直接取引用
    status: TradeStatus = TradeStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    # 固有アイテム用
    offered_unique_id: Optional[str] = None
    requested_unique_id: Optional[str] = None
    
    @classmethod
    def create_money_trade(cls, seller_id: str, offered_item_id: str, 
                          offered_item_count: int, requested_money: int,
                          trade_type: TradeType = TradeType.GLOBAL,
                          target_player_id: Optional[str] = None,
                          offered_unique_id: Optional[str] = None) -> "TradeOffer":
        """お金との取引オファーを作成"""
        return cls(
            trade_id=str(uuid.uuid4()),
            seller_id=seller_id,
            offered_item_id=offered_item_id,
            offered_item_count=offered_item_count,
            requested_money=requested_money,
            trade_type=trade_type,
            target_player_id=target_player_id,
            offered_unique_id=offered_unique_id
        )
    
    @classmethod
    def create_item_trade(cls, seller_id: str, offered_item_id: str,
                         offered_item_count: int, requested_item_id: str,
                         requested_item_count: int = 1,
                         trade_type: TradeType = TradeType.GLOBAL,
                         target_player_id: Optional[str] = None,
                         offered_unique_id: Optional[str] = None,
                         requested_unique_id: Optional[str] = None) -> "TradeOffer":
        """アイテム同士の取引オファーを作成"""
        return cls(
            trade_id=str(uuid.uuid4()),
            seller_id=seller_id,
            offered_item_id=offered_item_id,
            offered_item_count=offered_item_count,
            requested_money=0,
            requested_item_id=requested_item_id,
            requested_item_count=requested_item_count,
            trade_type=trade_type,
            target_player_id=target_player_id,
            offered_unique_id=offered_unique_id,
            requested_unique_id=requested_unique_id
        )
    
    def is_money_trade(self) -> bool:
        """お金との取引かどうか"""
        return self.requested_item_id is None and self.requested_money > 0
    
    def is_item_trade(self) -> bool:
        """アイテム同士の取引かどうか"""
        return self.requested_item_id is not None
    
    def is_direct_trade(self) -> bool:
        """直接取引かどうか"""
        return self.trade_type == TradeType.DIRECT
    
    def is_for_player(self, player_id: str) -> bool:
        """特定のプレイヤー向けの取引かどうか"""
        return self.target_player_id == player_id
    
    def can_be_accepted_by(self, player_id: str) -> bool:
        """指定プレイヤーが受託可能かどうか"""
        if self.status != TradeStatus.ACTIVE:
            return False 
        if self.seller_id == player_id:
            return False  # 自分の出品は受託できない
        if self.target_player_id and self.target_player_id != player_id:
            return False  # 直接取引で対象外
        return True
    
    def get_trade_summary(self) -> str:
        """取引内容の要約を取得"""
        offered = f"{self.offered_item_id} x{self.offered_item_count}"
        if self.offered_unique_id:
            offered += f" (固有ID:{self.offered_unique_id})"
        
        if self.is_money_trade():
            requested = f"{self.requested_money}ゴールド"
        else:
            requested = f"{self.requested_item_id} x{self.requested_item_count}"
            if self.requested_unique_id:
                requested += f" (固有ID:{self.requested_unique_id})"
        
        trade_type_str = "直接取引" if self.is_direct_trade() else "グローバル取引"
        return f"[{trade_type_str}] {offered} ⇄ {requested}"
    
    def __str__(self):
        return f"TradeOffer({self.trade_id[:8]}...): {self.get_trade_summary()}"
    
    def __repr__(self):
        return (f"TradeOffer(trade_id={self.trade_id}, seller_id={self.seller_id}, "
                f"offered={self.offered_item_id}x{self.offered_item_count}, "
                f"requested={'money' if self.is_money_trade() else 'item'}, "
                f"status={self.status.value})") 