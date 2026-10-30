from ai_rpg_world.application.common.event_delivery import (
    CommandEventHandlerRegistrarPort,
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.trade.handlers.trade_event_handler import TradeEventHandler
from ai_rpg_world.domain.trade.event.trade_event import (
    TradeAcceptedEvent,
    TradeCancelledEvent,
    TradeDeclinedEvent,
    TradeOfferedEvent,
)


class TradeEventHandlerRegistry:
    """取引イベントハンドラの登録"""

    def __init__(self, trade_event_handler: TradeEventHandler):
        self._trade_event_handler = trade_event_handler

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
