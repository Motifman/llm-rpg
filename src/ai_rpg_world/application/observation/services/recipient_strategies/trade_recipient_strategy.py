"""取引系イベントの観測配信先解決戦略"""

from typing import Any, List, Optional

from ai_rpg_world.application.observation.contracts.interfaces import (
    IRecipientResolutionStrategy,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.event.trade_event import (
    TradeAcceptedEvent,
    TradeCancelledEvent,
    TradeDeclinedEvent,
    TradeOfferedEvent,
)
from ai_rpg_world.domain.trade.enum.trade_enum import TradeType
from ai_rpg_world.domain.trade.repository.trade_repository import TradeRepository
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId


class TradeRecipientStrategy(IRecipientResolutionStrategy):
    """取引イベントの配信先を解決する。"""

    def __init__(self, trade_repository: Optional[TradeRepository] = None) -> None:
        self._trade_repository = trade_repository

    def supports(self, event: Any) -> bool:
        return isinstance(
            event,
            (TradeOfferedEvent, TradeAcceptedEvent, TradeCancelledEvent, TradeDeclinedEvent),
        )

    def resolve(self, event: Any) -> List[PlayerId]:
        if isinstance(event, TradeOfferedEvent):
            result: List[PlayerId] = [event.seller_id]
            if (
                event.trade_scope is not None
                and event.trade_scope.trade_type == TradeType.DIRECT
                and event.trade_scope.target_player_id is not None
            ):
                target = event.trade_scope.target_player_id
                if target.value != event.seller_id.value:
                    result.append(target)
            return result

        if isinstance(event, TradeAcceptedEvent):
            result = [event.buyer_id]
            if self._trade_repository is not None:
                trade = self._trade_repository.find_by_id(event.aggregate_id)
                if trade is not None and trade.seller_id.value != event.buyer_id.value:
                    result.append(trade.seller_id)
            return result

        if isinstance(event, TradeCancelledEvent):
            if self._trade_repository is None:
                return []
            trade = self._trade_repository.find_by_id(event.aggregate_id)
            if trade is None:
                return []
            result = [trade.seller_id]
            if (
                trade.trade_scope is not None
                and trade.trade_scope.trade_type == TradeType.DIRECT
                and trade.trade_scope.target_player_id is not None
                and trade.trade_scope.target_player_id.value != trade.seller_id.value
            ):
                result.append(trade.trade_scope.target_player_id)
            return result

        if isinstance(event, TradeDeclinedEvent):
            if self._trade_repository is None:
                return []
            trade = self._trade_repository.find_by_id(event.aggregate_id)
            if trade is None:
                return []
            result = [event.decliner_id]
            if trade.seller_id.value != event.decliner_id.value:
                result.append(trade.seller_id)
            return result

        return []
