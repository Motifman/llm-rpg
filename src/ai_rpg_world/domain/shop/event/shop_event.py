from dataclasses import dataclass
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.shop.value_object.shop_listing_price import ShopListingPrice
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId


@dataclass(frozen=True)
class ShopCreatedEvent(BaseDomainEvent[ShopId, "ShopAggregate"]):
    """ショップ開設イベント"""
    spot_id: SpotId
    location_area_id: LocationAreaId
    owner_id: PlayerId


@dataclass(frozen=True)
class ShopItemListedEvent(BaseDomainEvent[ShopId, "ShopAggregate"]):
    """ショップ出品イベント"""
    listing_id: ShopListingId
    item_instance_id: ItemInstanceId
    price_per_unit: ShopListingPrice
    listed_by: PlayerId


@dataclass(frozen=True)
class ShopItemUnlistedEvent(BaseDomainEvent[ShopId, "ShopAggregate"]):
    """ショップ取り下げイベント"""
    listing_id: ShopListingId
    unlisted_by: PlayerId


@dataclass(frozen=True)
class ShopItemPurchasedEvent(BaseDomainEvent[ShopId, "ShopAggregate"]):
    """ショップ購入イベント"""
    listing_id: ShopListingId
    item_instance_id: ItemInstanceId
    buyer_id: PlayerId
    quantity: int
    total_gold: int
    seller_id: PlayerId


@dataclass(frozen=True)
class ShopClosedEvent(BaseDomainEvent[ShopId, "ShopAggregate"]):
    """ショップ閉鎖イベント（オーナーによる閉鎖）"""
    closed_by: PlayerId
