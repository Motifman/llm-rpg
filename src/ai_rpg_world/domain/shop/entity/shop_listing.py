"""ショップリスト（集約内エンティティ）"""
from dataclasses import dataclass
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.shop.value_object.shop_listing_price import ShopListingPrice
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


@dataclass(frozen=True)
class ShopListing:
    """ショップの出品リスト（集約内エンティティ）

    在庫は持たない。在庫は紐づく ItemInstance の quantity で表現し、
    ItemRepository 側の ItemAggregate で管理する。
    """
    listing_id: ShopListingId
    item_instance_id: ItemInstanceId
    price_per_unit: ShopListingPrice
    listed_by: PlayerId
