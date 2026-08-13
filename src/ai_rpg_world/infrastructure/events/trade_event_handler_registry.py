from typing import TYPE_CHECKING
from ai_rpg_world.application.common.event_delivery import (
    CommandEventHandlerRegistrarPort,
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.trade.event.trade_event import (
    TradeOfferedEvent,
    TradeAcceptedEvent,
    TradeCancelledEvent,
    TradeDeclinedEvent,
)
from ai_rpg_world.application.trade.handlers.trade_event_handler import TradeEventHandler

if TYPE_CHECKING:
    from ai_rpg_world.domain.common.event_handler import EventHandler


class TradeEventHandlerRegistry:
    """取引イベントハンドラの登録"""

    def __init__(self, trade_event_handler: TradeEventHandler):
        self._trade_event_handler = trade_event_handler

    def register_handlers(self, event_publisher: EventPublisher) -> None:
        """全イベントハンドラをEventPublisherに登録"""

        event_publisher.register_handler(
            TradeOfferedEvent,
            self._create_event_handler(self._trade_event_handler.handle_trade_offered),
            is_synchronous=False,
        )
        event_publisher.register_handler(
            TradeAcceptedEvent,
            self._create_event_handler(self._trade_event_handler.handle_trade_accepted),
            is_synchronous=False,
        )
        event_publisher.register_handler(
            TradeCancelledEvent,
            self._create_event_handler(self._trade_event_handler.handle_trade_cancelled),
            is_synchronous=False,
        )
        event_publisher.register_handler(
            TradeDeclinedEvent,
            self._create_event_handler(self._trade_event_handler.handle_trade_declined),
            is_synchronous=False,
        )

    def register_command_handlers(
        self,
        registrar: CommandEventHandlerRegistrarPort,
    ) -> None:
        """取引read model更新をcommit後配送として明示登録する。"""
        registrar.register_after_commit(
            TradeOfferedEvent,
            self._trade_event_handler.handle_trade_offered,
            channel=DeliveryChannel.READ_MODEL,
            guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )
        registrar.register_after_commit(
            TradeAcceptedEvent,
            self._trade_event_handler.handle_trade_accepted,
            channel=DeliveryChannel.READ_MODEL,
            guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )
        registrar.register_after_commit(
            TradeCancelledEvent,
            self._trade_event_handler.handle_trade_cancelled,
            channel=DeliveryChannel.READ_MODEL,
            guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )
        registrar.register_after_commit(
            TradeDeclinedEvent,
            self._trade_event_handler.handle_trade_declined,
            channel=DeliveryChannel.READ_MODEL,
            guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )

    def _create_event_handler(self, handler_method) -> "EventHandler":
        """イベントハンドラオブジェクトを作成"""
        class EventHandlerImpl:
            def __init__(self, method):
                self._method = method

            def handle(self, event):
                self._method(event)

        return EventHandlerImpl(handler_method)
