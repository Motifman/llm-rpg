from dataclasses import dataclass, field
from typing import Optional
from enum import Enum
from datetime import datetime
import uuid


class TradeType(Enum):
    """取引タイプ"""
    GLOBAL = "global"     # グローバル取引所
    DIRECT = "direct"     # 直接取引（同一Spot）


class TradeStatus(Enum):
    """取引ステータス"""
    ACTIVE = "active"         # 募集中
    COMPLETED = "completed"   # 成立
    CANCELLED = "cancelled"   # キャンセル


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
    target_agent_id: Optional[str] = None  # 直接取引用
    status: TradeStatus = TradeStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    
    @classmethod
    def create_money_trade(cls, seller_id: str, offered_item_id: str, 
                          offered_item_count: int, requested_money: int,
                          trade_type: TradeType = TradeType.GLOBAL,
                          target_agent_id: Optional[str] = None) -> "TradeOffer":
        """お金との取引オファーを作成"""
        return cls(
            trade_id=str(uuid.uuid4()),
            seller_id=seller_id,
            offered_item_id=offered_item_id,
            offered_item_count=offered_item_count,
            requested_money=requested_money,
            trade_type=trade_type,
            target_agent_id=target_agent_id
        )
    
    @classmethod
    def create_item_trade(cls, seller_id: str, offered_item_id: str,
                         offered_item_count: int, requested_item_id: str,
                         requested_item_count: int = 1,
                         trade_type: TradeType = TradeType.GLOBAL,
                         target_agent_id: Optional[str] = None) -> "TradeOffer":
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
            target_agent_id=target_agent_id
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
    
    def is_for_agent(self, agent_id: str) -> bool:
        """特定のエージェント向けの取引かどうか"""
        return self.target_agent_id == agent_id
    
    def can_be_accepted_by(self, agent_id: str) -> bool:
        """指定エージェントが受託可能かどうか"""
        if self.status != TradeStatus.ACTIVE:
            return False
        if self.seller_id == agent_id:
            return False  # 自分の出品は受託できない
        if self.target_agent_id and self.target_agent_id != agent_id:
            return False  # 直接取引で対象外
        return True
    
    def get_trade_summary(self) -> str:
        """取引内容の要約を取得"""
        offered = f"{self.offered_item_id} x{self.offered_item_count}"
        
        if self.is_money_trade():
            requested = f"{self.requested_money}ゴールド"
        else:
            requested = f"{self.requested_item_id} x{self.requested_item_count}"
        
        trade_type_str = "直接取引" if self.is_direct_trade() else "グローバル取引"
        return f"[{trade_type_str}] {offered} ⇄ {requested}"
    
    def __str__(self):
        return f"TradeOffer({self.trade_id[:8]}...): {self.get_trade_summary()}"
    
    def __repr__(self):
        return (f"TradeOffer(trade_id={self.trade_id}, seller_id={self.seller_id}, "
                f"offered={self.offered_item_id}x{self.offered_item_count}, "
                f"requested={'money' if self.is_money_trade() else 'item'}, "
                f"status={self.status.value})") 