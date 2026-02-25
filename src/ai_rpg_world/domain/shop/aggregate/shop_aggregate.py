"""ショップ集約"""
from typing import Optional, Dict, Set
from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.shop.value_object.shop_listing_price import ShopListingPrice
from ai_rpg_world.domain.shop.entity.shop_listing import ShopListing
from ai_rpg_world.domain.shop.event.shop_event import (
    ShopCreatedEvent,
    ShopItemListedEvent,
    ShopItemUnlistedEvent,
    ShopItemPurchasedEvent,
    ShopClosedEvent,
)
from ai_rpg_world.domain.shop.exception.shop_exception import (
    NotShopOwnerException,
    ListingNotFoundException,
)
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId


class ShopAggregate(AggregateRoot):
    """ショップ集約

    ロケーション（SpotId + LocationAreaId）に紐づくプレイヤー運営ショップ。
    複数オーナーを想定し、オーナーのみが出品・取り下げ・店操作が可能。
    """

    def __init__(
        self,
        shop_id: ShopId,
        spot_id: SpotId,
        location_area_id: LocationAreaId,
        owner_ids: Set[PlayerId],
        name: str,
        description: str,
        listings: Optional[Dict[ShopListingId, ShopListing]] = None,
    ):
        super().__init__()
        self._shop_id = shop_id
        self._spot_id = spot_id
        self._location_area_id = location_area_id
        self._owner_ids = owner_ids.copy() if owner_ids else set()
        self._name = name
        self._description = description
        self._listings = dict(listings) if listings else {}
        # 将来用: lot_id: Optional[LotId] = None

    @classmethod
    def create(
        cls,
        shop_id: ShopId,
        spot_id: SpotId,
        location_area_id: LocationAreaId,
        owner_id: PlayerId,
        name: str = "",
        description: str = "",
    ) -> "ShopAggregate":
        """新規ショップを作成"""
        shop = cls(
            shop_id=shop_id,
            spot_id=spot_id,
            location_area_id=location_area_id,
            owner_ids={owner_id},
            name=name,
            description=description,
            listings={},
        )
        event = ShopCreatedEvent.create(
            aggregate_id=shop_id,
            aggregate_type="ShopAggregate",
            spot_id=spot_id,
            location_area_id=location_area_id,
            owner_id=owner_id,
        )
        shop.add_event(event)
        return shop

    @property
    def shop_id(self) -> ShopId:
        return self._shop_id

    @property
    def spot_id(self) -> SpotId:
        return self._spot_id

    @property
    def location_area_id(self) -> LocationAreaId:
        return self._location_area_id

    @property
    def owner_ids(self) -> Set[PlayerId]:
        return self._owner_ids.copy()

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def listings(self) -> Dict[ShopListingId, ShopListing]:
        return self._listings.copy()

    def is_owner(self, player_id: PlayerId) -> bool:
        """指定プレイヤーがオーナーかどうか"""
        return player_id in self._owner_ids

    def add_owner(self, player_id: PlayerId) -> None:
        """オーナーを追加"""
        self._owner_ids.add(player_id)

    def remove_owner(self, player_id: PlayerId) -> None:
        """オーナーを削除"""
        self._owner_ids.discard(player_id)

    def list_item(
        self,
        listing_id: ShopListingId,
        item_instance_id: ItemInstanceId,
        price_per_unit: ShopListingPrice,
        listed_by: PlayerId,
    ) -> None:
        """アイテムを出品する。listed_by はオーナーである必要がある。"""
        if listed_by not in self._owner_ids:
            raise NotShopOwnerException(
                f"Player {listed_by} is not an owner of shop {self._shop_id}"
            )
        listing = ShopListing(
            listing_id=listing_id,
            item_instance_id=item_instance_id,
            price_per_unit=price_per_unit,
            listed_by=listed_by,
        )
        self._listings[listing_id] = listing
        event = ShopItemListedEvent.create(
            aggregate_id=self._shop_id,
            aggregate_type="ShopAggregate",
            listing_id=listing_id,
            item_instance_id=item_instance_id,
            price_per_unit=price_per_unit,
            listed_by=listed_by,
        )
        self.add_event(event)

    def unlist_item(self, listing_id: ShopListingId, player_id: PlayerId) -> None:
        """オーナーがリストを取り下げる"""
        if player_id not in self._owner_ids:
            raise NotShopOwnerException(
                f"Player {player_id} is not an owner of shop {self._shop_id}"
            )
        if listing_id not in self._listings:
            raise ListingNotFoundException(
                f"Listing {listing_id} not found in shop {self._shop_id}"
            )
        del self._listings[listing_id]
        event = ShopItemUnlistedEvent.create(
            aggregate_id=self._shop_id,
            aggregate_type="ShopAggregate",
            listing_id=listing_id,
            unlisted_by=player_id,
        )
        self.add_event(event)

    def remove_listing(self, listing_id: ShopListingId) -> None:
        """リストを削除する（在庫切れなど。オーナーによる取り下げは unlist_item を使う）"""
        if listing_id not in self._listings:
            raise ListingNotFoundException(
                f"Listing {listing_id} not found in shop {self._shop_id}"
            )
        del self._listings[listing_id]

    def get_listing(self, listing_id: ShopListingId) -> Optional[ShopListing]:
        """指定リストを取得"""
        return self._listings.get(listing_id)

    def record_purchase(
        self,
        listing_id: ShopListingId,
        buyer_id: PlayerId,
        quantity: int,
        total_gold: int,
    ) -> None:
        """購入を記録し ShopItemPurchasedEvent を発行する（ReadModel 更新用）。

        購入処理の一環としてアプリケーション層から呼ばれる。
        remove_listing の前に呼ぶこと（リスト情報がイベントに必要）。
        """
        listing = self._listings.get(listing_id)
        if listing is None:
            raise ListingNotFoundException(
                f"Listing {listing_id} not found in shop {self._shop_id}"
            )
        event = ShopItemPurchasedEvent.create(
            aggregate_id=self._shop_id,
            aggregate_type="ShopAggregate",
            listing_id=listing_id,
            item_instance_id=listing.item_instance_id,
            buyer_id=buyer_id,
            quantity=quantity,
            total_gold=total_gold,
            seller_id=listing.listed_by,
        )
        self.add_event(event)

    def close(self, closed_by: PlayerId) -> None:
        """ショップを閉鎖する。オーナーのみ実行可能。閉鎖イベントを発行する。"""
        if closed_by not in self._owner_ids:
            raise NotShopOwnerException(
                f"Player {closed_by} is not an owner of shop {self._shop_id}"
            )
        event = ShopClosedEvent.create(
            aggregate_id=self._shop_id,
            aggregate_type="ShopAggregate",
            closed_by=closed_by,
        )
        self.add_event(event)
