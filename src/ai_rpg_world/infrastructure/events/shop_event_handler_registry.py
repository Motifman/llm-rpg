"""ショップイベントハンドラの登録"""

from ai_rpg_world.application.common.event_delivery import (
    CommandEventHandlerRegistrarPort,
    DeliveryChannel,
    DeliveryGuarantee,
)
from ai_rpg_world.application.shop.handlers.shop_event_handler import ShopEventHandler
from ai_rpg_world.domain.shop.event.shop_event import (
    ShopCreatedEvent,
    ShopItemListedEvent,
    ShopItemPurchasedEvent,
    ShopItemUnlistedEvent,
)


class ShopEventHandlerRegistry:
    """ショップイベントハンドラの登録"""

    def __init__(self, shop_event_handler: ShopEventHandler):
        self._shop_event_handler = shop_event_handler

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
