"""ショップリストReadModelリポジトリインターフェース"""

from abc import abstractmethod

from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.shop.read_model.shop_listing_read_model import ShopListingReadModel
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.shop.value_object.shop_listing_id import ShopListingId


class ShopListingReadModelRepository(Repository[ShopListingReadModel, ShopListingId]):
    """ショップリストReadModelリポジトリインターフェース

    リストは listing_id がグローバル一意のため、find_by_id は ShopListingId で検索する。
    """

    @abstractmethod
    def find_by_shop_id(self, shop_id: ShopId) -> list[ShopListingReadModel]:
        """ショップIDに紐づく出品リスト一覧を取得する"""
        pass
