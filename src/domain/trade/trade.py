from dataclasses import dataclass
from typing import Optional
from datetime import datetime
from domain.trade.trade_enum import TradeType, TradeStatus
from src.domain.trade.exception import (
    InvalidTradeStatusException,
    CannotAcceptOwnTradeException,
    CannotAcceptTradeWithOtherPlayerException,
    CannotCancelTradeWithOtherPlayerException,
)


@dataclass
class TradeItem:
    item_id: Optional[int] = None
    count: Optional[int] = None
    unique_id: Optional[int] = None

    def __post_init__(self):
        """インスタンス生成後のバリデーション"""
        is_stackable = self.item_id is not None and self.count is not None
        is_unique = self.item_id is not None and self.unique_id is not None
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


# TODO まずは簡易実装として物々交換を禁止
@dataclass
class TradeOffer:
    """取引オファー"""
    trade_id: int
    seller_id: int
    offered_item: TradeItem
    requested_gold: int
    created_at: datetime
    trade_type: TradeType = TradeType.GLOBAL
    target_player_id: Optional[int] = None  # 直接取引用
    status: TradeStatus = TradeStatus.ACTIVE
    version: int = 0
    buyer_id: Optional[int] = None
    
    def __post_init__(self):
        """インスタンス生成後のバリデーション"""
        if self.trade_id is None:
            raise ValueError("trade_id cannot be None.")
        if self.seller_id is None:
            raise ValueError("seller_id cannot be None.")
        # 初期化時はACTIVE状態のみ許可（COMPLETEDやCANCELLEDは不正）
        if self.status != TradeStatus.ACTIVE:
            raise InvalidTradeStatusException(f"status must be ACTIVE: {self.status}")
        if self.buyer_id is not None:
            raise InvalidTradeStatusException(f"buyer_id must be None when initializing: {self.buyer_id}")
        # DIRECTトレードの場合はtarget_player_idが必要、GLOBAL/その他の場合は不要
        if self.trade_type == TradeType.DIRECT and self.target_player_id is None:
            raise InvalidTradeStatusException(f"target_player_id is required for DIRECT trade: {self.target_player_id}, {self.trade_type}")
        if self.trade_type != TradeType.DIRECT and self.target_player_id is not None:
            raise InvalidTradeStatusException(f"target_player_id must be None when trade_type is not DIRECT: {self.target_player_id}, {self.trade_type}")
        if self.requested_gold <= 0:
            raise InvalidTradeStatusException(f"requested_gold must be greater than 0: {self.requested_gold}")
    
    @classmethod
    def create_trade(
        cls,
        trade_id: int,
        seller_id: int,
        requested_gold: int,
        offered_item_id: int,
        created_at: datetime,
        trade_type: TradeType = TradeType.GLOBAL,
        target_player_id: Optional[int] = None,
        offered_item_count: Optional[int] = None,
        offered_unique_id: Optional[int] = None,
    ) -> "TradeOffer":
        """お金との取引オファーを作成"""
        if offered_item_count is not None:
            trade_item = TradeItem.stackable(offered_item_id, offered_item_count)
        elif offered_unique_id is not None:
            trade_item = TradeItem.unique(offered_item_id, offered_unique_id)
        else:
            raise InvalidTradeStatusException(f"offered_item_count or offered_unique_id must be provided: {offered_item_id}, {offered_item_count}, {offered_unique_id}")

        return cls(
            trade_id=trade_id,
            seller_id=seller_id,
            offered_item=trade_item,
            requested_gold=requested_gold,
            trade_type=trade_type,
            target_player_id=target_player_id,
            created_at=created_at,
        )
    
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

    def accept_by(self, buyer_id: int):
        """取引を受託"""
        if self.status != TradeStatus.ACTIVE:
            raise InvalidTradeStatusException(f"Trade is not active: {self.status}")
        if self.seller_id == buyer_id:
            raise CannotAcceptOwnTradeException(f"Cannot accept trade with yourself: {self.seller_id}, {buyer_id}")
        if self.is_direct_trade() and self.target_player_id != buyer_id:
            raise CannotAcceptTradeWithOtherPlayerException(f"Cannot accept trade with other player: {self.target_player_id}, {buyer_id}")

        self.buyer_id = buyer_id
        self.status = TradeStatus.COMPLETED

    def cancel_by(self, player_id: int) -> None:
        """取引をキャンセル"""
        if self.status != TradeStatus.ACTIVE:
            raise InvalidTradeStatusException(f"Trade is already completed or cancelled: {self.status}")
        if self.seller_id != player_id:
            raise CannotCancelTradeWithOtherPlayerException(f"Cannot cancel trade with other player: {self.seller_id}, {player_id}")
        self.status = TradeStatus.CANCELLED
    
    def __str__(self):
        return f"TradeOffer({self.trade_id}): {self.get_trade_summary()}"
    
    def __repr__(self):
        return (f"TradeOffer(trade_id={self.trade_id}, seller_id={self.seller_id}, "
                f"offered={self.offered_item.item_id}x{self.offered_item.count}, "
                f"requested={self.requested_gold} G, "
                f"status={self.status.value})") 