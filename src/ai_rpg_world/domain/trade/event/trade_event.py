from dataclasses import dataclass

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.value_object.trade_scope import TradeScope
from ai_rpg_world.domain.trade.value_object.trade_requested_gold import TradeRequestedGold
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId


@dataclass(frozen=True)
class TradeOfferedEvent(BaseDomainEvent[TradeId, "TradeAggregate"]):
    """取引提案イベント"""
    seller_id: PlayerId
    offered_item_id: ItemInstanceId
    requested_gold: TradeRequestedGold
    trade_scope: TradeScope


@dataclass(frozen=True)
class TradeAcceptedEvent(BaseDomainEvent[TradeId, "TradeAggregate"]):
    """取引受託イベント"""
    buyer_id: PlayerId


@dataclass(frozen=True)
class TradeCancelledEvent(BaseDomainEvent[TradeId, "TradeAggregate"]):
    """取引キャンセルイベント"""
