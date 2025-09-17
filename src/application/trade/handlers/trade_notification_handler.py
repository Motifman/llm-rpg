from src.domain.common.event_handler import EventHandler
from src.domain.trade.trade_events import DirectTradeOfferedEvent, TradeCancelledEvent, TradeExecutedEvent
from src.domain.trade.trade_notification import TradeNotification
from src.domain.trade.trade_notification_repository import TradeNotificationRepository


class DirectTradeOfferedNotificationHandler(EventHandler[DirectTradeOfferedEvent]):
    """取引作成時の通知ハンドラー、直接取引の場合のみ対象プレイヤーに通知"""
    def __init__(self, trade_notification_repository: TradeNotificationRepository):
        self._trade_notification_repository = trade_notification_repository

    def handle(self, event: DirectTradeOfferedEvent):
        if event.trade_type.value == "direct" and event.target_player_id:
            trade_notification = TradeNotification.create(
                trade_notification_id=self._trade_notification_repository.generate_trade_notification_id(),
                trade_id=event.trade_id,
                recipient_player_id=event.target_player_id,
                message=f"あなたが対象の取引 (ID: {event.trade_id}) が作成されました！",
                read=False,
                created_at=event.occurred_at,
                updated_at=event.occurred_at,
            )
            self._trade_notification_repository.save(trade_notification)


class TradeExecutedNotificationHandler(EventHandler[TradeExecutedEvent]):
    """取引成立時の通知ハンドラー、売り手と買い手の両方に通知"""
    def __init__(self, trade_notification_repository: TradeNotificationRepository):
        self._trade_notification_repository = trade_notification_repository

    def handle(self, event: TradeExecutedEvent):
        # 売り手に通知
        trade_notification = TradeNotification.create(
            trade_notification_id=self._trade_notification_repository.generate_trade_notification_id(),
            trade_id=event.trade_id,
            recipient_player_id=event.seller_id,
            message=f"{event.buyer_name}と取引 (ID: {event.trade_id}) が成立しました！",
            read=False,
            created_at=event.occurred_at,
            updated_at=event.occurred_at,
        )
        self._trade_notification_repository.save(trade_notification)
        # 買い手に通知
        trade_notification = TradeNotification.create(
            trade_notification_id=self._trade_notification_repository.generate_trade_notification_id(),
            trade_id=event.trade_id,
            recipient_player_id=event.buyer_id,
            message=f"{event.seller_name}と取引 (ID: {event.trade_id}) が成立しました！",
            read=False,
            created_at=event.occurred_at,
            updated_at=event.occurred_at,
        )
        self._trade_notification_repository.save(trade_notification)


class TradeCancelledNotificationHandler(EventHandler[TradeCancelledEvent]):
    """取引キャンセル時の通知ハンドラー、直接取引の場合のみ対象プレイヤーに通知"""
    def __init__(self, trade_notification_repository: TradeNotificationRepository):
        self._trade_notification_repository = trade_notification_repository

    def handle(self, event: TradeCancelledEvent):
        if event.trade_type.value == "direct" and event.target_player_id:
            trade_notification = TradeNotification.create(
                trade_notification_id=self._trade_notification_repository.generate_trade_notification_id(),
                trade_id=event.trade_id,
                recipient_player_id=event.target_player_id,
                message=f"あなたが対象の取引 (ID: {event.trade_id}) がキャンセルされました。",
                read=False,
                created_at=event.occurred_at,
                updated_at=event.occurred_at,
            )
            self._trade_notification_repository.save(trade_notification)