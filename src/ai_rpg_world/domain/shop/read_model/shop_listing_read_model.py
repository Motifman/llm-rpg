"""ショップリストReadModel"""
from datetime import datetime
from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


@dataclass
class ShopListingReadModel:
    """ショップ出品リスト用ReadModel

    ショップの出品一覧表示に必要な情報を非正規化して保持する。
    CQRSパターンのReadModelとして機能する。
    """

    shop_id: int
    listing_id: int
    item_instance_id: int
    item_name: str
    item_spec_id: int
    price_per_unit: int
    quantity: int
    listed_by: int
    listed_at: Optional[datetime] = None

    @classmethod
    def create(
        cls,
        shop_id: ShopId,
        listing_id: ShopListingId,
        item_instance_id: ItemInstanceId,
        item_name: str,
        item_spec_id: int,
        price_per_unit: int,
        quantity: int,
        listed_by: PlayerId,
        listed_at: Optional[datetime] = None,
    ) -> "ShopListingReadModel":
        """出品情報からReadModelを作成"""
        return cls(
            shop_id=int(shop_id),
            listing_id=int(listing_id),
            item_instance_id=int(item_instance_id),
            item_name=item_name,
            item_spec_id=item_spec_id,
            price_per_unit=price_per_unit,
            quantity=quantity,
            listed_by=int(listed_by),
            listed_at=listed_at,
        )
