from src.domain.common.domain_event import DomainEvent
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, kw_only=True)
class TradeNotificationCreated(DomainEvent):
    trade_notification_id: int
    trade_id: int
    recipient_player_id: int
    message: str
    read: bool
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, kw_only=True)
class TradeNotificationRead(DomainEvent):
    trade_notification_id: int