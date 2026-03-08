"""ショップ系イベントの観測配信先解決戦略"""

from typing import Any, List, Optional

from ai_rpg_world.application.observation.contracts.interfaces import (
    IRecipientResolutionStrategy,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.shop.event.shop_event import (
    ShopClosedEvent,
    ShopCreatedEvent,
    ShopItemListedEvent,
    ShopItemPurchasedEvent,
    ShopItemUnlistedEvent,
)
from ai_rpg_world.domain.shop.repository.shop_repository import ShopRepository
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


class ShopRecipientStrategy(IRecipientResolutionStrategy):
    """ショップイベントの配信先を解決する。"""

    def __init__(
        self,
        player_status_repository: PlayerStatusRepository,
        shop_repository: Optional[ShopRepository] = None,
    ) -> None:
        self._player_status_repository = player_status_repository
        self._shop_repository = shop_repository

    def supports(self, event: Any) -> bool:
        return isinstance(
            event,
            (
                ShopCreatedEvent,
                ShopItemListedEvent,
                ShopItemUnlistedEvent,
                ShopItemPurchasedEvent,
                ShopClosedEvent,
            ),
        )

    def resolve(self, event: Any) -> List[PlayerId]:
        if isinstance(event, ShopCreatedEvent):
            # オーナー本人 + そのスポットにいるプレイヤー
            return [event.owner_id] + self._players_at_spot(event.spot_id)

        if isinstance(event, ShopItemPurchasedEvent):
            # 購入者 + 売り手（listed_by）
            return [event.buyer_id, event.seller_id]

        if isinstance(event, (ShopItemListedEvent, ShopItemUnlistedEvent, ShopClosedEvent)):
            # そのショップが存在するスポットのプレイヤー（条件付き）。spot が引けない場合は本人のみ。
            spot_id = self._spot_id_from_shop(event.aggregate_id)
            if spot_id is None:
                # 最低限: listed/unlisted は操作した本人、closed は閉鎖者
                if isinstance(event, ShopItemListedEvent):
                    return [event.listed_by]
                if isinstance(event, ShopItemUnlistedEvent):
                    return [event.unlisted_by]
                if isinstance(event, ShopClosedEvent):
                    return [event.closed_by]
                return []
            return self._players_at_spot(spot_id)

        return []

    def _players_at_spot(self, spot_id: SpotId) -> List[PlayerId]:
        all_statuses = self._player_status_repository.find_all()
        return [
            s.player_id
            for s in all_statuses
            if s.current_spot_id is not None and s.current_spot_id.value == spot_id.value
        ]

    def _spot_id_from_shop(self, shop_id) -> Optional[SpotId]:
        if self._shop_repository is None:
            return None
        shop = self._shop_repository.find_by_id(shop_id)
        if shop is None:
            return None
        return shop.spot_id

