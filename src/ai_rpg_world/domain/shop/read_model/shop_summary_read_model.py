"""ショップサマリReadModel"""
from datetime import datetime
from dataclasses import dataclass
from typing import List

from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


@dataclass
class ShopSummaryReadModel:
    """ショップ一覧・ロケーション別ショップ用ReadModel

    ショップの基本情報を非正規化して保持し、クエリを高速化する。
    CQRSパターンのReadModelとして機能する。
    """

    shop_id: int
    spot_id: int
    location_area_id: int
    name: str
    description: str
    owner_ids: List[int]
    listing_count: int
    created_at: datetime

    @classmethod
    def create(
        cls,
        shop_id: ShopId,
        spot_id: SpotId,
        location_area_id: LocationAreaId,
        name: str,
        description: str,
        owner_ids: List[PlayerId],
        listing_count: int,
        created_at: datetime,
    ) -> "ShopSummaryReadModel":
        """ショップ情報からReadModelを作成"""
        return cls(
            shop_id=int(shop_id),
            spot_id=spot_id.value,
            location_area_id=location_area_id.value,
            name=name,
            description=description,
            owner_ids=[int(pid) for pid in owner_ids],
            listing_count=listing_count,
            created_at=created_at,
        )
