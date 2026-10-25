"""ショップイベントハンドラの登録"""
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from ai_rpg_world.application.common.event_delivery import (
    CommandEventHandlerRegistrarPort,
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.shop.handlers.shop_event_handler import ShopEventHandler
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.common.event_handler import EventHandler
from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.shop.event.shop_event import (
    ShopCreatedEvent,
    ShopItemListedEvent,
    ShopItemPurchasedEvent,
    ShopItemUnlistedEvent,
)

if TYPE_CHECKING:
    from ai_rpg_world.domain.common.event_handler import EventHandler


class ShopEventHandlerRegistry:
    """ショップイベントハンドラの登録"""

    def __init__(self, shop_event_handler: ShopEventHandler):
        self._shop_event_handler = shop_event_handler

    def register_handlers(self, event_publisher: EventPublisher[DomainEvent]) -> None:
        """全イベントハンドラをEventPublisherに登録"""
        event_publisher.register_handler(
            ShopCreatedEvent,
            self._create_event_handler(self._shop_event_handler.handle_shop_created),
            is_synchronous=False,
        )
        event_publisher.register_handler(
            ShopItemListedEvent,
            self._create_event_handler(self._shop_event_handler.handle_shop_item_listed),
            is_synchronous=False,
        )
        event_publisher.register_handler(
            ShopItemUnlistedEvent,
            self._create_event_handler(self._shop_event_handler.handle_shop_item_unlisted),
            is_synchronous=False,
        )
        event_publisher.register_handler(
            ShopItemPurchasedEvent,
            self._create_event_handler(
                self._shop_event_handler.handle_shop_item_purchased
            ),
            is_synchronous=False,
        )

    def register_command_handlers(self, registrar: CommandEventHandlerRegistrarPort) -> None:
        """既存のイベント対応を、確定の前後を保って共通基盤へ登録する。"""
        registrar.register_after_commit(
            ShopCreatedEvent, self._shop_event_handler.handle_shop_created,
            channel=DeliveryChannel.READ_MODEL, guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )
        registrar.register_after_commit(
            ShopItemListedEvent, self._shop_event_handler.handle_shop_item_listed,
            channel=DeliveryChannel.READ_MODEL, guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )
        registrar.register_after_commit(
            ShopItemUnlistedEvent, self._shop_event_handler.handle_shop_item_unlisted,
            channel=DeliveryChannel.READ_MODEL, guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )
        registrar.register_after_commit(
            ShopItemPurchasedEvent, self._shop_event_handler.handle_shop_item_purchased,
            channel=DeliveryChannel.READ_MODEL, guarantee=DeliveryGuarantee.DURABLE_RETRY,
        )

    def _create_event_handler(
        self, handler_method: Callable[[Any], None]
    ) -> "EventHandler[Any]":
        """イベントハンドラオブジェクトを作成"""
        class EventHandlerImpl(EventHandler[Any]):
            def __init__(self, method: Callable[[Any], None]) -> None:
                self._method = method

            def handle(self, event: Any) -> None:
                self._method(event)

        return EventHandlerImpl(handler_method)
