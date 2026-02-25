"""LocationEstablishment 集約 - ロケーション単位で1施設のみの割当を管理"""
from typing import Optional

from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.world.value_object.location_slot_id import LocationSlotId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.enum.world_enum import EstablishmentType
from ai_rpg_world.domain.world.event.location_establishment_events import (
    LocationEstablishmentClaimedEvent,
    LocationEstablishmentReleasedEvent,
)
from ai_rpg_world.domain.world.exception.map_exception import (
    LocationAlreadyOccupiedException,
    LocationNotOccupiedException,
)


class LocationEstablishmentAggregate(AggregateRoot):
    """ロケーションスロット集約。

    1ロケーション（SpotId + LocationAreaId）に最大1施設のみ割り当て可能。
    解放時は集約を削除せず、establishment_type / establishment_id を None にする。
    """

    def __init__(
        self,
        id: LocationSlotId,
        spot_id: SpotId,
        location_area_id: LocationAreaId,
        establishment_type: Optional[EstablishmentType] = None,
        establishment_id: Optional[int] = None,
    ):
        super().__init__()
        self._id = id
        self._spot_id = spot_id
        self._location_area_id = location_area_id
        self._establishment_type = establishment_type
        self._establishment_id = establishment_id

    @property
    def id(self) -> LocationSlotId:
        return self._id

    @property
    def spot_id(self) -> SpotId:
        return self._spot_id

    @property
    def location_area_id(self) -> LocationAreaId:
        return self._location_area_id

    @property
    def establishment_type(self) -> Optional[EstablishmentType]:
        return self._establishment_type

    @property
    def establishment_id(self) -> Optional[int]:
        return self._establishment_id

    def is_occupied(self) -> bool:
        return self._establishment_type is not None and self._establishment_id is not None

    @classmethod
    def create(
        cls,
        spot_id: SpotId,
        location_area_id: LocationAreaId,
    ) -> "LocationEstablishmentAggregate":
        """未割当の新規スロットを作成する。"""
        slot_id = LocationSlotId(spot_id=spot_id, location_area_id=location_area_id)
        return cls(
            id=slot_id,
            spot_id=spot_id,
            location_area_id=location_area_id,
            establishment_type=None,
            establishment_id=None,
        )

    def claim(self, establishment_type: EstablishmentType, establishment_id: int) -> None:
        """ロケーションを施設で占有する。既に割当済みの場合は LocationAlreadyOccupiedException。"""
        if self.is_occupied():
            raise LocationAlreadyOccupiedException(
                f"Location already occupied: spot_id={self._spot_id}, location_area_id={self._location_area_id}, "
                f"current={self._establishment_type}"
            )
        self._establishment_type = establishment_type
        self._establishment_id = establishment_id
        event = LocationEstablishmentClaimedEvent.create(
            aggregate_id=self._id,
            aggregate_type="LocationEstablishmentAggregate",
            spot_id=self._spot_id,
            location_area_id=self._location_area_id,
            establishment_type=establishment_type,
            establishment_id=establishment_id,
        )
        self.add_event(event)

    def release(self) -> None:
        """割当を解除する。未割当の場合は LocationNotOccupiedException（仕様 3.1）。"""
        if not self.is_occupied():
            raise LocationNotOccupiedException(
                f"Location is not occupied, cannot release: spot_id={self._spot_id}, location_area_id={self._location_area_id}"
            )
        prev_type = self._establishment_type
        prev_id = self._establishment_id
        self._establishment_type = None
        self._establishment_id = None
        event = LocationEstablishmentReleasedEvent.create(
            aggregate_id=self._id,
            aggregate_type="LocationEstablishmentAggregate",
            spot_id=self._spot_id,
            location_area_id=self._location_area_id,
            previous_establishment_type=prev_type,
            previous_establishment_id=prev_id,
        )
        self.add_event(event)
