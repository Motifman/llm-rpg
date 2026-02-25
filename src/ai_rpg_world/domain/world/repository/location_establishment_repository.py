"""LocationEstablishment リポジトリインターフェース"""
from abc import abstractmethod
from typing import Optional

from ai_rpg_world.domain.common.repository import Repository
from ai_rpg_world.domain.world.aggregate.location_establishment_aggregate import (
    LocationEstablishmentAggregate,
)
from ai_rpg_world.domain.world.value_object.location_slot_id import LocationSlotId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId


class LocationEstablishmentRepository(
    Repository[LocationEstablishmentAggregate, LocationSlotId]
):
    """ロケーションスロット（施設割当）のリポジトリ"""

    @abstractmethod
    def find_by_spot_and_location(
        self,
        spot_id: SpotId,
        location_area_id: LocationAreaId,
    ) -> Optional[LocationEstablishmentAggregate]:
        """指定ロケーションのスロットを取得。実装では LocationSlotId を組み立てて find_by_id を呼ぶ形でよい。"""
        pass
