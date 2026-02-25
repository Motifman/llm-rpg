"""
InMemoryShopRepository - ショップ関連のインメモリリポジトリ
"""
from typing import List, Optional, Dict
from ai_rpg_world.domain.shop.repository.shop_repository import ShopRepository
from ai_rpg_world.domain.shop.aggregate.shop_aggregate import ShopAggregate
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from .in_memory_repository_base import InMemoryRepositoryBase
from .in_memory_data_store import InMemoryDataStore
from ai_rpg_world.domain.common.unit_of_work import UnitOfWork


class InMemoryShopRepository(ShopRepository, InMemoryRepositoryBase):
    """ショップリポジトリのインメモリ実装"""

    def __init__(
        self,
        data_store: Optional[InMemoryDataStore] = None,
        unit_of_work: Optional[UnitOfWork] = None,
    ):
        super().__init__(data_store, unit_of_work)

    @property
    def _shops(self) -> Dict[ShopId, ShopAggregate]:
        return self._data_store.shops

    def find_by_id(self, shop_id: ShopId) -> Optional[ShopAggregate]:
        pending = self._get_pending_aggregate(shop_id)
        if pending is not None:
            return self._clone(pending)
        return self._clone(self._shops.get(shop_id))

    def find_by_ids(self, shop_ids: List[ShopId]) -> List[ShopAggregate]:
        return [x for sid in shop_ids for x in [self.find_by_id(sid)] if x is not None]

    def save(self, shop: ShopAggregate) -> ShopAggregate:
        cloned_shop = self._clone(shop)

        def operation():
            self._shops[cloned_shop.shop_id] = cloned_shop
            return cloned_shop

        self._register_aggregate(shop)
        self._register_pending_if_uow(shop.shop_id, shop)
        return self._execute_operation(operation)

    def delete(self, shop_id: ShopId) -> bool:
        def operation():
            if shop_id in self._shops:
                del self._shops[shop_id]
                return True
            return False

        return self._execute_operation(operation)

    def find_all(self) -> List[ShopAggregate]:
        return [self._clone(s) for s in self._shops.values()]

    def generate_shop_id(self) -> ShopId:
        shop_id = self._data_store.next_shop_id
        self._data_store.next_shop_id += 1
        return ShopId(shop_id)

    def generate_listing_id(self) -> ShopListingId:
        listing_id = self._data_store.next_shop_listing_id
        self._data_store.next_shop_listing_id += 1
        return ShopListingId(listing_id)

    def find_by_spot_and_location(
        self,
        spot_id: SpotId,
        location_area_id: LocationAreaId,
    ) -> Optional[ShopAggregate]:
        for shop in self._shops.values():
            if shop.spot_id == spot_id and shop.location_area_id == location_area_id:
                return self._clone(shop)
        return None
