"""
InMemoryShopListingReadModelRepository - ショップリストReadModelのインメモリ実装
"""

from ai_rpg_world.domain.shop.read_model.shop_listing_read_model import ShopListingReadModel
from ai_rpg_world.domain.shop.repository.shop_listing_read_model_repository import (
    ShopListingReadModelRepository,
)
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId


class InMemoryShopListingReadModelRepository(ShopListingReadModelRepository):
    """ショップリストReadModelのインメモリリポジトリ

    listing_id はグローバル一意のため、キーは ShopListingId とする。
    """

    def __init__(self) -> None:
        self._listings: dict[ShopListingId, ShopListingReadModel] = {}

    def find_by_id(self, entity_id: ShopListingId) -> ShopListingReadModel | None:
        """listing_idで出品リストを検索"""
        return self._listings.get(entity_id)

    def find_by_ids(self, entity_ids: list[ShopListingId]) -> list[ShopListingReadModel]:
        """listing_idのリストで出品リストを検索"""
        return [s for lid in entity_ids for s in [self._listings.get(lid)] if s is not None]

    def save(self, entity: ShopListingReadModel) -> ShopListingReadModel:
        """出品リストを保存"""
        self._listings[ShopListingId(entity.listing_id)] = entity
        return entity

    def delete(self, entity_id: ShopListingId) -> bool:
        """出品リストを削除"""
        if entity_id in self._listings:
            del self._listings[entity_id]
            return True
        return False

    def find_all(self) -> list[ShopListingReadModel]:
        """全ての出品リストを取得"""
        return list(self._listings.values())

    def find_by_shop_id(self, shop_id: ShopId) -> list[ShopListingReadModel]:
        """ショップIDに紐づく出品リスト一覧を取得"""
        return [s for s in self._listings.values() if s.shop_id == int(shop_id)]
