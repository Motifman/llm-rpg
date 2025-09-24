from src.domain.common.aggregate_root import AggregateRoot
from datetime import datetime, Optional
from src.domain.trade.trade_notification_events import TradeNotificationCreated, TradeNotificationRead


class TradeNotification(AggregateRoot):
    def __init__(self, trade_notification_id: int, trade_id: int, recipient_player_id: int, message: str, read: bool, created_at: datetime, updated_at: datetime):
        self._trade_notification_id = trade_notification_id
        self._trade_id = trade_id
        self._recipient_player_id = recipient_player_id
        self._message = message
        self._read = read
        self._created_at = created_at
        self._updated_at = updated_at
    
    @classmethod
    def create(cls, trade_notification_id: int, trade_id: int, recipient_player_id: int, message: str, read: bool, created_at: Optional[datetime], updated_at: Optional[datetime]):
        if created_at is None:
            created_at = datetime.now()
        if updated_at is None:
            updated_at = datetime.now()

        trade_notification = cls(
            trade_notification_id=trade_notification_id,
            trade_id=trade_id,
            recipient_player_id=recipient_player_id,
            message=message,
            read=read,
            created_at=created_at,
            updated_at=updated_at,
        )
        trade_notification.add_event(TradeNotificationCreated.create(
            aggregate_id=trade_notification_id,
            aggregate_type="trade_notification",
            trade_notification_id=trade_notification_id,
            trade_id=trade_id,
            recipient_player_id=recipient_player_id,
            message=message,
            read=read,
            created_at=created_at,
            updated_at=updated_at,
        ))
        return trade_notification

    def mark_as_read(self):
        self._read = True
        self._updated_at = datetime.now()
        self.add_event(TradeNotificationRead.create(
            aggregate_id=self._trade_notification_id,
            aggregate_type="trade_notification",
            trade_notification_id=self._trade_notification_id,
        ))