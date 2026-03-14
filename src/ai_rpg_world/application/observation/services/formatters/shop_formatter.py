"""ショップイベント用の観測 formatter。"""

from typing import Any, Optional

from ai_rpg_world.application.observation.contracts.dtos import ObservationOutput
from ai_rpg_world.application.observation.services.formatters._formatter_context import (
    ObservationFormatterContext,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.shop.event.shop_event import (
    ShopClosedEvent,
    ShopCreatedEvent,
    ShopItemListedEvent,
    ShopItemPurchasedEvent,
    ShopItemUnlistedEvent,
)


class ShopObservationFormatter:
    """ShopCreatedEvent / ShopItemListedEvent / ShopItemPurchasedEvent 等を処理する。"""

    def __init__(self, context: ObservationFormatterContext) -> None:
        self._context = context

    def format(
        self,
        event: Any,
        recipient_player_id: PlayerId,
    ) -> Optional[ObservationOutput]:
        if isinstance(event, ShopCreatedEvent):
            return self._format_shop_created(event, recipient_player_id)
        if isinstance(event, ShopItemListedEvent):
            return self._format_shop_item_listed(event, recipient_player_id)
        if isinstance(event, ShopItemUnlistedEvent):
            return self._format_shop_item_unlisted(event, recipient_player_id)
        if isinstance(event, ShopItemPurchasedEvent):
            return self._format_shop_item_purchased(event, recipient_player_id)
        if isinstance(event, ShopClosedEvent):
            return self._format_shop_closed(event, recipient_player_id)
        return None

    def _format_shop_created(
        self, event: ShopCreatedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "ショップが開設されました。"
        shop_id = event.aggregate_id.value
        structured = {"type": "shop_created", "shop_id_value": shop_id}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
        )

    def _format_shop_item_listed(
        self, event: ShopItemListedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._context.name_resolver.item_instance_name(event.item_instance_id)
        prose = f"ショップに{item_name}が出品されました。"
        shop_id_value = event.aggregate_id.value
        structured = {
            "type": "shop_item_listed",
            "item_name": item_name,
            "shop_id_value": shop_id_value,
        }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
        )

    def _format_shop_item_unlisted(
        self, event: ShopItemUnlistedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "ショップの出品が取り下げられました。"
        shop_id_value = event.aggregate_id.value
        structured = {"type": "shop_item_unlisted", "shop_id_value": shop_id_value}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
        )

    def _format_shop_item_purchased(
        self, event: ShopItemPurchasedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        item_name = self._context.name_resolver.item_instance_name(event.item_instance_id)
        is_buyer = event.buyer_id.value == recipient_id.value
        buyer_name = self._context.name_resolver.player_name(event.buyer_id)
        seller_name = self._context.name_resolver.player_name(event.seller_id)
        shop_id = event.aggregate_id.value
        if is_buyer:
            prose = f"{item_name}を{event.quantity}個購入しました（支払い: {event.total_gold}ゴールド）。"
            structured = {
                "type": "shop_purchase",
                "role": "buyer",
                "item_name": item_name,
                "shop_id_value": shop_id,
            }
        else:
            prose = f"{buyer_name}が{item_name}を{event.quantity}個購入しました（受取: {event.total_gold}ゴールド）。"
            structured = {
                "type": "shop_purchase",
                "role": "seller",
                "item_name": item_name,
                "buyer": buyer_name,
                "seller": seller_name,
                "shop_id_value": shop_id,
            }
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="self_only",
            schedules_turn=True,
        )

    def _format_shop_closed(
        self, event: ShopClosedEvent, recipient_id: PlayerId
    ) -> Optional[ObservationOutput]:
        prose = "ショップが閉鎖されました。"
        shop_id_value = event.aggregate_id.value
        structured = {"type": "shop_closed", "shop_id_value": shop_id_value}
        return ObservationOutput(
            prose=prose,
            structured=structured,
            observation_category="social",
        )
