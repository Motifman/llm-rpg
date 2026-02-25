"""
InMemoryShopSummaryReadModelRepository - ショップサマリReadModelのインメモリ実装
"""
from typing import Dict, List, Optional

from ai_rpg_world.domain.shop.repository.shop_summary_read_model_repository import (
    ShopSummaryReadModelRepository,
)
from ai_rpg_world.domain.shop.read_model.shop_summary_read_model import ShopSummaryReadModel
from ai_rpg_world.domain.shop.value_object.shop_id import ShopId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId


class InMemoryShopSummaryReadModelRepository(ShopSummaryReadModelRepository):
    """ショップサマリReadModelのインメモリリポジトリ"""

    def __init__(self) -> None:
        self._summaries: Dict[ShopId, ShopSummaryReadModel] = {}

    def find_by_id(self, entity_id: ShopId) -> Optional[ShopSummaryReadModel]:
        """IDでショップサマリを検索"""
        return self._summaries.get(entity_id)

    def find_by_ids(self, entity_ids: List[ShopId]) -> List[ShopSummaryReadModel]:
        """IDのリストでショップサマリを検索"""
        return [s for sid in entity_ids for s in [self._summaries.get(sid)] if s is not None]

    def save(self, entity: ShopSummaryReadModel) -> ShopSummaryReadModel:
        """ショップサマリを保存"""
        self._summaries[ShopId(entity.shop_id)] = entity
        return entity

    def delete(self, entity_id: ShopId) -> bool:
        """ショップサマリを削除"""
        if entity_id in self._summaries:
            del self._summaries[entity_id]
            return True
        return False

    def find_all(self) -> List[ShopSummaryReadModel]:
        """全てのショップサマリを取得"""
        return list(self._summaries.values())

    def find_by_spot_and_location(
        self,
        spot_id: SpotId,
        location_area_id: LocationAreaId,
    ) -> Optional[ShopSummaryReadModel]:
        """スポットとロケーションエリアでショップサマリを取得"""
        for s in self._summaries.values():
            if s.spot_id == spot_id.value and s.location_area_id == location_area_id.value:
                return s
        return None

    def find_all_by_spot_id(self, spot_id: SpotId) -> List[ShopSummaryReadModel]:
        """スポットIDに紐づくショップサマリ一覧を取得"""
        return [s for s in self._summaries.values() if s.spot_id == spot_id.value]
