from dataclasses import dataclass
from datetime import datetime

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.trade.value_object.trade_id import TradeId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.trade.value_object.trade_scope import TradeScope
from ai_rpg_world.domain.trade.value_object.trade_requested_gold import TradeRequestedGold
from ai_rpg_world.domain.trade.value_object.trade_listing_projection import TradeListingProjection
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId


@dataclass(frozen=True)
class TradeOfferedEvent(BaseDomainEvent[TradeId, "TradeAggregate"]):
    """取引提案イベント"""
    seller_id: PlayerId
    offered_item_id: ItemInstanceId
    requested_gold: TradeRequestedGold
    trade_scope: TradeScope
    listing_projection: TradeListingProjection
    trade_created_at: datetime


@dataclass(frozen=True)
class TradeAcceptedEvent(BaseDomainEvent[TradeId, "TradeAggregate"]):
    """取引受託イベント"""
    buyer_id: PlayerId
    buyer_display_name: str
    listing_projection: TradeListingProjection
    seller_id: PlayerId
    offered_item_id: ItemInstanceId
    requested_gold: TradeRequestedGold
    trade_created_at: datetime


@dataclass(frozen=True)
class TradeCancelledEvent(BaseDomainEvent[TradeId, "TradeAggregate"]):
    """取引キャンセルイベント"""


@dataclass(frozen=True)
class TradeDeclinedEvent(BaseDomainEvent[TradeId, "TradeAggregate"]):
    """取引拒否イベント"""
    decliner_id: PlayerId
