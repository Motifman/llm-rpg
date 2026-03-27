"""ショップ系イベントの観測配信先解決戦略"""

from typing import Any, List

from ai_rpg_world.application.observation.contracts.interfaces import (
    IPlayerAudienceQueryPort,
    IRecipientResolutionStrategy,
)
from ai_rpg_world.application.observation.services.observed_event_registry import (
    ObservedEventRegistry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.shop.event.shop_event import (
    ShopClosedEvent,
    ShopCreatedEvent,
    ShopItemListedEvent,
    ShopItemPurchasedEvent,
    ShopItemUnlistedEvent,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class ShopRecipientStrategy(IRecipientResolutionStrategy):
    """ショップイベントの配信先を解決する。"""

    _STRATEGY_KEY = "shop"

    def __init__(
        self,
        observed_event_registry: ObservedEventRegistry,
        player_audience_query: IPlayerAudienceQueryPort,
    ) -> None:
        self._registry = observed_event_registry
        self._player_audience_query = player_audience_query

    def supports(self, event: Any) -> bool:
        return self._registry.get_strategy_for_event(event) == self._STRATEGY_KEY

    def resolve(self, event: Any) -> List[PlayerId]:
        if isinstance(event, ShopCreatedEvent):
            # オーナー本人 + そのスポットにいるプレイヤー
            return [event.owner_id] + self._player_audience_query.players_at_spot(event.spot_id)

        if isinstance(event, ShopItemPurchasedEvent):
            # 購入者 + 売り手（listed_by）
            return [event.buyer_id, event.seller_id]

        if isinstance(event, (ShopItemListedEvent, ShopItemUnlistedEvent, ShopClosedEvent)):
            return self._player_audience_query.players_at_spot(event.spot_id)

        return []

