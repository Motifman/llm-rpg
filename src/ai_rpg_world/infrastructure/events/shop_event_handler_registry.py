"""ショップイベントハンドラの登録"""
from typing import TYPE_CHECKING

from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.shop.event.shop_event import (
    ShopCreatedEvent,
    ShopItemListedEvent,
    ShopItemUnlistedEvent,
    ShopItemPurchasedEvent,
)
from ai_rpg_world.application.shop.handlers.shop_event_handler import ShopEventHandler

if TYPE_CHECKING:
    from ai_rpg_world.domain.common.event_handler import EventHandler


class ShopEventHandlerRegistry:
    """ショップイベントハンドラの登録"""

    def __init__(self, shop_event_handler: ShopEventHandler):
        self._shop_event_handler = shop_event_handler

    def register_handlers(self, event_publisher: EventPublisher) -> None:
        """全イベントハンドラをEventPublisherに登録"""
        event_publisher.register_handler(
            ShopCreatedEvent,
            self._create_event_handler(self._shop_event_handler.handle_shop_created),
        )
        event_publisher.register_handler(
            ShopItemListedEvent,
            self._create_event_handler(self._shop_event_handler.handle_shop_item_listed),
        )
        event_publisher.register_handler(
            ShopItemUnlistedEvent,
            self._create_event_handler(self._shop_event_handler.handle_shop_item_unlisted),
        )
        event_publisher.register_handler(
            ShopItemPurchasedEvent,
            self._create_event_handler(
                self._shop_event_handler.handle_shop_item_purchased
            ),
        )

    def _create_event_handler(self, handler_method) -> "EventHandler":
        """イベントハンドラオブジェクトを作成"""
        class EventHandlerImpl:
            def __init__(self, method):
                self._method = method

            def handle(self, event):
                self._method(event)

        return EventHandlerImpl(handler_method)
