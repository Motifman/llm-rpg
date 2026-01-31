from typing import TYPE_CHECKING
from src.domain.common.event_publisher import EventPublisher
from src.domain.trade.event.trade_event import (
    TradeOfferedEvent,
    TradeAcceptedEvent,
    TradeCancelledEvent
)
from src.application.trade.handlers.trade_event_handler import TradeEventHandler

if TYPE_CHECKING:
    from src.domain.common.event_handler import EventHandler


class TradeEventHandlerRegistry:
    """取引イベントハンドラの登録"""

    def __init__(self, trade_event_handler: TradeEventHandler):
        self._trade_event_handler = trade_event_handler

    def register_handlers(self, event_publisher: EventPublisher) -> None:
        """全イベントハンドラをEventPublisherに登録"""

        event_publisher.register_handler(
            TradeOfferedEvent,
            self._create_event_handler(self._trade_event_handler.handle_trade_offered)
        )
        event_publisher.register_handler(
            TradeAcceptedEvent,
            self._create_event_handler(self._trade_event_handler.handle_trade_accepted)
        )
        event_publisher.register_handler(
            TradeCancelledEvent,
            self._create_event_handler(self._trade_event_handler.handle_trade_cancelled)
        )

    def _create_event_handler(self, handler_method) -> "EventHandler":
        """イベントハンドラオブジェクトを作成"""
        class EventHandlerImpl:
            def __init__(self, method):
                self._method = method

            def handle(self, event):
                self._method(event)

        return EventHandlerImpl(handler_method)
