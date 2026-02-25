"""ショップサマリReadModelリポジトリインターフェース"""
from abc import abstractmethod
from typing import List, Optional

from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.shop.read_model.shop_summary_read_model import ShopSummaryReadModel
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId


class ShopSummaryReadModelRepository(Repository[ShopSummaryReadModel, ShopId]):
    """ショップサマリReadModelリポジトリインターフェース"""

    @abstractmethod
    def find_by_spot_and_location(
        self,
        spot_id: SpotId,
        location_area_id: LocationAreaId,
    ) -> Optional[ShopSummaryReadModel]:
        """スポットとロケーションエリアでショップサマリを取得する"""
        pass

    @abstractmethod
    def find_all_by_spot_id(self, spot_id: SpotId) -> List[ShopSummaryReadModel]:
        """スポットIDに紐づくショップサマリ一覧を取得する"""
        pass
