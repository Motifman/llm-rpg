from abc import abstractmethod
from typing import Optional
from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.shop.aggregate.shop_aggregate import ShopAggregate
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId


class ShopRepository(Repository[ShopAggregate, ShopId]):
    """ショップリポジトリインターフェース"""

    @abstractmethod
    def generate_shop_id(self) -> ShopId:
        """新規ショップIDを生成"""
        pass

    @abstractmethod
    def generate_listing_id(self) -> ShopListingId:
        """新規リストIDを生成（ショップ内で一意ならグローバル連番でよい）"""
        pass

    @abstractmethod
    def find_by_spot_and_location(
        self,
        spot_id: SpotId,
        location_area_id: LocationAreaId,
    ) -> Optional[ShopAggregate]:
        """指定ロケーションのショップを取得（1ロケーション1ショップ）"""
        pass
