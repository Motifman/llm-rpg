"""LocationSlotId - ロケーションスロットの複合識別子（SpotId + LocationAreaId）"""
from dataclasses import dataclass
from typing import Union

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId


@dataclass(frozen=True)
class LocationSlotId:
    """ロケーションスロットの一意識別子。

    (SpotId, LocationAreaId) の複合キー。1ロケーション = 1集約の ID として使用する。
    不変条件は SpotId / LocationAreaId の正の整数検証に委譲する。
    """
    spot_id: SpotId
    location_area_id: LocationAreaId

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, LocationSlotId):
            return NotImplemented
        return self.spot_id == other.spot_id and self.location_area_id == other.location_area_id

    def __hash__(self) -> int:
        return hash((self.spot_id, self.location_area_id))

    @classmethod
    def create(
        cls,
        spot_id: Union[SpotId, int],
        location_area_id: Union[LocationAreaId, int],
    ) -> "LocationSlotId":
        """SpotId / LocationAreaId または int から作成"""
        sid = spot_id if isinstance(spot_id, SpotId) else SpotId.create(spot_id)
        lid = location_area_id if isinstance(location_area_id, LocationAreaId) else LocationAreaId.create(location_area_id)
        return cls(spot_id=sid, location_area_id=lid)
