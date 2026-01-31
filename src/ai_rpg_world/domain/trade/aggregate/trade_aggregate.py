from typing import Optional
from datetime import datetime

from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.trade.enum.trade_enum import TradeStatus
from ai_rpg_world.domain.trade.exception.trade_exception import (
    InvalidTradeStatusException,
    CannotAcceptOwnTradeException,
    CannotAcceptTradeWithOtherPlayerException,
    CannotCancelTradeWithOtherPlayerException,
)
from ai_rpg_world.domain.trade.event.trade_event import (
    TradeOfferedEvent,
    TradeAcceptedEvent,
    TradeCancelledEvent,
)
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.trade.value_object.trade_requested_gold import TradeRequestedGold
from ai_rpg_world.domain.trade.value_object.trade_scope import TradeScope
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class TradeAggregate(AggregateRoot):
    """取引集約"""

    def __init__(
        self,
        trade_id: TradeId,
        seller_id: PlayerId,
        offered_item_id: ItemInstanceId,
        requested_gold: TradeRequestedGold,
        created_at: datetime,
        trade_scope: TradeScope,
        status: TradeStatus,
        version: int = 0,
        buyer_id: Optional[PlayerId] = None,
    ):
        super().__init__()
        self.trade_id = trade_id
        self.seller_id = seller_id
        self.offered_item_id = offered_item_id
        self.requested_gold = requested_gold
        self.created_at = created_at
        self.trade_scope = trade_scope
        self.status = status
        self.version = version
        self.buyer_id = buyer_id

    @classmethod
    def create_new_trade(
        cls,
        trade_id: TradeId,
        seller_id: PlayerId,
        offered_item_id: ItemInstanceId,
        requested_gold: TradeRequestedGold,
        created_at: datetime,
        trade_scope: TradeScope,
    ) -> "TradeAggregate":
        """新規取引作成"""
        trade = cls(
            trade_id=trade_id,
            seller_id=seller_id,
            offered_item_id=offered_item_id,
            requested_gold=requested_gold,
            created_at=created_at,
            trade_scope=trade_scope,
            status=TradeStatus.ACTIVE,
            buyer_id=None,
        )

        # ドメインイベント発行
        event = TradeOfferedEvent.create(
            aggregate_id=trade_id,
            aggregate_type="TradeAggregate",
            seller_id=seller_id,
            offered_item_id=offered_item_id,
            requested_gold=requested_gold,
            trade_scope=trade_scope,
        )
        trade.add_event(event)

        return trade

    def is_active(self) -> bool:
        """取引がアクティブかどうか"""
        return self.status == TradeStatus.ACTIVE

    def is_direct_trade(self) -> bool:
        """プレイヤーを指定した直接取引かどうか"""
        return self.trade_scope.is_direct()

    def is_for_player(self, player_id: PlayerId) -> bool:
        """特定のプレイヤー向けの取引かどうか"""
        return self.trade_scope.is_direct() and self.trade_scope.target_player_id == player_id

    def can_be_accepted_by(self, player_id: PlayerId) -> bool:
        """指定プレイヤーが受託可能かどうか"""
        if self.status != TradeStatus.ACTIVE:
            return False
        if self.seller_id == player_id:
            return False  # 自分の出品は受託できない
        if self.trade_scope.is_direct() and self.trade_scope.target_player_id != player_id:
            return False  # 直接取引で対象外
        return True

    def accept_by(self, buyer_id: PlayerId):
        """取引を受託"""
        if self.status != TradeStatus.ACTIVE:
            raise InvalidTradeStatusException(f"Trade is not active: {self.status}")
        if self.seller_id == buyer_id:
            raise CannotAcceptOwnTradeException(f"Cannot accept trade with yourself: {self.seller_id}, {buyer_id}")
        if self.is_direct_trade() and self.trade_scope.target_player_id != buyer_id:
            raise CannotAcceptTradeWithOtherPlayerException(f"Cannot accept trade with other player: {self.trade_scope.target_player_id}, {buyer_id}")

        self.buyer_id = buyer_id
        self.status = TradeStatus.COMPLETED

        # ドメインイベント発行
        event = TradeAcceptedEvent.create(
            aggregate_id=self.trade_id,
            aggregate_type="TradeAggregate",
            buyer_id=buyer_id,
        )
        self.add_event(event)

    def cancel_by(self, player_id: PlayerId) -> None:
        """取引をキャンセル"""
        if self.status != TradeStatus.ACTIVE:
            raise InvalidTradeStatusException(f"Trade is already completed or cancelled: {self.status}")
        if self.seller_id != player_id:
            raise CannotCancelTradeWithOtherPlayerException(f"Cannot cancel trade with other player: {self.seller_id}, {player_id}")
        self.status = TradeStatus.CANCELLED

        # ドメインイベント発行
        event = TradeCancelledEvent.create(
            aggregate_id=self.trade_id,
            aggregate_type="TradeAggregate",
        )
        self.add_event(event)