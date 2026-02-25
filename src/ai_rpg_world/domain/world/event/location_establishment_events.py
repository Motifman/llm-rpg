"""LocationEstablishment 集約のドメインイベント"""
from dataclasses import dataclass
from typing import Optional

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.world.value_object.location_slot_id import LocationSlotId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.enum.world_enum import EstablishmentType


@dataclass(frozen=True)
class LocationEstablishmentClaimedEvent(BaseDomainEvent[LocationSlotId, str]):
    """ロケーションに施設が割り当てられたイベント"""
    spot_id: SpotId
    location_area_id: LocationAreaId
    establishment_type: EstablishmentType
    establishment_id: int


@dataclass(frozen=True)
class LocationEstablishmentReleasedEvent(BaseDomainEvent[LocationSlotId, str]):
    """ロケーションの割当が解除されたイベント"""
    spot_id: SpotId
    location_area_id: LocationAreaId
    previous_establishment_type: EstablishmentType
    previous_establishment_id: int
