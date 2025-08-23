from dataclasses import dataclass
from typing import Optional, List
from datetime import datetime
from src.domain.common.aggregate_root import AggregateRoot
from src.domain.trade.trade_enum import TradeType, TradeStatus
from src.domain.trade.trade_exception import (
    InvalidTradeStatusException,
    CannotAcceptOwnTradeException,
    CannotAcceptTradeWithOtherPlayerException,
    CannotCancelTradeWithOtherPlayerException,
)
from src.domain.trade.trade_events import (
    TradeCreatedEvent,
    TradeExecutedEvent,
    TradeCancelledEvent,
    DirectTradeOfferedEvent
)


@dataclass
class TradeItem:
    item_id: int
    count: Optional[int] = None
    unique_id: Optional[int] = None

    def __post_init__(self):
        """インスタンス生成後のバリデーション"""
        is_stackable = self.count is not None
        is_unique = self.unique_id is not None
        if not (is_stackable or is_unique):
            raise InvalidTradeStatusException(f"TradeItem must have either count or unique_id: {self.item_id}, {self.count}, {self.unique_id}")
        if is_stackable and is_unique:
            raise InvalidTradeStatusException(f"TradeItem cannot have both count and unique_id: {self.item_id}, {self.count}, {self.unique_id}")
        if is_stackable and self.count <= 0:
            raise InvalidTradeStatusException(f"Count must be greater than 0: {self.item_id}, {self.count}, {self.unique_id}")
    
    @classmethod
    def stackable(cls, item_id: int, count: int) -> "TradeItem":
        """スタック可能アイテム用のファクトリメソッド"""
        return cls(item_id=item_id, count=count, unique_id=None)

    @classmethod
    def unique(cls, item_id: int, unique_id: int) -> "TradeItem":
        """固有アイテム用のファクトリメソッド"""
        return cls(item_id=item_id, count=None, unique_id=unique_id)

    def is_stackable(self) -> bool:
        """スタック可能アイテムかどうか"""
        return self.count is not None
    

# TODO まずは簡易実装として物々交換を禁止
class TradeOffer(AggregateRoot):
    """取引オファー"""
    
    def __init__(
        self,
        trade_id: int,
        seller_id: int,
        offered_item: TradeItem,
        requested_gold: int,
        created_at: datetime,
        trade_type: TradeType = TradeType.GLOBAL,
        target_player_id: Optional[int] = None,  # 直接取引用
        status: TradeStatus = TradeStatus.ACTIVE,
        version: int = 0,
        buyer_id: Optional[int] = None,
    ):
        super().__init__()
        
        # 引数のバリデーション（元の __post_init__ と同じロジック）
        if trade_id is None:
            raise ValueError("trade_id cannot be None.")
        if seller_id is None:
            raise ValueError("seller_id cannot be None.")
        # 初期化時はACTIVE状態のみ許可（COMPLETEDやCANCELLEDは不正）
        if status != TradeStatus.ACTIVE:
            raise InvalidTradeStatusException(f"status must be ACTIVE: {status}")
        if buyer_id is not None:
            raise InvalidTradeStatusException(f"buyer_id must be None when initializing: {buyer_id}")
        # DIRECTトレードの場合はtarget_player_idが必要、GLOBAL/その他の場合は不要
        if trade_type == TradeType.DIRECT and target_player_id is None:
            raise InvalidTradeStatusException(f"target_player_id is required for DIRECT trade: {target_player_id}, {trade_type}")
        if trade_type != TradeType.DIRECT and target_player_id is not None:
            raise InvalidTradeStatusException(f"target_player_id must be None when trade_type is not DIRECT: {target_player_id}, {trade_type}")
        if requested_gold <= 0:
            raise InvalidTradeStatusException(f"requested_gold must be greater than 0: {requested_gold}")
        
        # 属性の設定
        self.trade_id = trade_id
        self.seller_id = seller_id
        self.offered_item = offered_item
        self.requested_gold = requested_gold
        self.created_at = created_at
        self.trade_type = trade_type
        self.target_player_id = target_player_id
        self.status = status
        self.version = version
        self.buyer_id = buyer_id
    
    @classmethod
    def create_trade(
        cls,
        trade_id: int,
        seller_id: int,
        requested_gold: int,
        trade_item: TradeItem,
        created_at: datetime,
        trade_type: TradeType = TradeType.GLOBAL,
        target_player_id: Optional[int] = None,
        seller_name: str = None,
        target_player_name: str = None,
    ) -> "TradeOffer":
        """お金との取引オファーを作成"""
        trade_offer = cls(
            trade_id=trade_id,
            seller_id=seller_id,
            offered_item=trade_item,
            requested_gold=requested_gold,
            trade_type=trade_type,
            target_player_id=target_player_id,
            created_at=created_at,
        )
        
        # ドメインイベントを発行
        if seller_name:
            if trade_type == TradeType.DIRECT and target_player_id and target_player_name:
                # 直接取引の場合は専用イベント
                event = DirectTradeOfferedEvent.create(
                    trade_id=trade_id,
                    seller_id=seller_id,
                    seller_name=seller_name,
                    target_player_id=target_player_id,
                    target_player_name=target_player_name,
                    offered_item_id=trade_item.item_id,
                    offered_item_count=trade_item.count,
                    offered_unique_id=trade_item.unique_id,
                    requested_gold=requested_gold
                )
            else:
                # グローバル取引の場合は通常の作成イベント
                event = TradeCreatedEvent.create(
                    trade_id=trade_id,
                    seller_id=seller_id,
                    seller_name=seller_name,
                    offered_item_id=trade_item.item_id,
                    offered_item_count=trade_item.count,
                    offered_unique_id=trade_item.unique_id,
                    requested_gold=requested_gold,
                    trade_type=trade_type,
                    target_player_id=target_player_id
                )
            trade_offer._domain_events.append(event)
        
        return trade_offer
    
    def is_active(self) -> bool:
        """取引がアクティブかどうか"""
        return self.status == TradeStatus.ACTIVE
    
    def is_direct_trade(self) -> bool:
        """プレイヤーを指定した直接取引かどうか"""
        return self.trade_type == TradeType.DIRECT
    
    def is_for_player(self, player_id: int) -> bool:
        """特定のプレイヤー向けの取引かどうか"""
        return self.target_player_id == player_id
    
    def can_be_accepted_by(self, player_id: int) -> bool:
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
        offered = f"{self.offered_item.item_id} x{self.offered_item.count}"
        if self.offered_item.unique_id:
            offered += f" (固有ID:{self.offered_item.unique_id})"
        requested = f"{self.requested_gold} G"
        trade_type_str = "直接取引" if self.is_direct_trade() else "グローバル取引"
        return f"[{trade_type_str}] {offered} ⇄ {requested}"

    def accept_by(self, buyer_id: int, buyer_name: str = None, seller_name: str = None):
        """取引を受託"""
        if self.status != TradeStatus.ACTIVE:
            raise InvalidTradeStatusException(f"Trade is not active: {self.status}")
        if self.seller_id == buyer_id:
            raise CannotAcceptOwnTradeException(f"Cannot accept trade with yourself: {self.seller_id}, {buyer_id}")
        if self.is_direct_trade() and self.target_player_id != buyer_id:
            raise CannotAcceptTradeWithOtherPlayerException(f"Cannot accept trade with other player: {self.target_player_id}, {buyer_id}")

        self.buyer_id = buyer_id
        self.status = TradeStatus.COMPLETED
        
        # ドメインイベントを発行
        if buyer_name and seller_name:
            event = TradeExecutedEvent.create(
                trade_id=self.trade_id,
                seller_id=self.seller_id,
                seller_name=seller_name,
                buyer_id=buyer_id,
                buyer_name=buyer_name,
                offered_item_id=self.offered_item.item_id,
                offered_item_count=self.offered_item.count,
                offered_unique_id=self.offered_item.unique_id,
                requested_gold=self.requested_gold,
                trade_type=self.trade_type
            )
            self.add_event(event)

    def cancel_by(self, player_id: int, seller_name: str = None) -> None:
        """取引をキャンセル"""
        if self.status != TradeStatus.ACTIVE:
            raise InvalidTradeStatusException(f"Trade is already completed or cancelled: {self.status}")
        if self.seller_id != player_id:
            raise CannotCancelTradeWithOtherPlayerException(f"Cannot cancel trade with other player: {self.seller_id}, {player_id}")
        self.status = TradeStatus.CANCELLED
        
        # ドメインイベントを発行
        if seller_name:
            event = TradeCancelledEvent.create(
                trade_id=self.trade_id,
                seller_id=self.seller_id,
                seller_name=seller_name,
                offered_item_id=self.offered_item.item_id,
                offered_item_count=self.offered_item.count,
                offered_unique_id=self.offered_item.unique_id,
                requested_gold=self.requested_gold,
                trade_type=self.trade_type,
                target_player_id=self.target_player_id
            )
            self.add_event(event)
    
    def __str__(self):
        return f"TradeOffer({self.trade_id}): {self.get_trade_summary()}"
    
    def __repr__(self):
        return (f"TradeOffer(trade_id={self.trade_id}, seller_id={self.seller_id}, "
                f"offered={self.offered_item.item_id}x{self.offered_item.count}, "
                f"requested={self.requested_gold} G, "
                f"status={self.status.value})")
 