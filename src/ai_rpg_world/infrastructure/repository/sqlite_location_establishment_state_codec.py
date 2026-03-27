"""Helpers for normalized LocationEstablishment persistence."""

from __future__ import annotations

from ai_rpg_world.domain.world.aggregate.location_establishment_aggregate import (
    LocationEstablishmentAggregate,
)
from ai_rpg_world.domain.world.enum.world_enum import EstablishmentType
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.location_slot_id import LocationSlotId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId


def build_location_establishment(
    *,
    spot_id: int,
    location_area_id: int,
    establishment_type: str | None,
    establishment_id: int | None,
) -> LocationEstablishmentAggregate:
    return LocationEstablishmentAggregate(
        id=LocationSlotId(spot_id=SpotId(spot_id), location_area_id=LocationAreaId(location_area_id)),
        spot_id=SpotId(spot_id),
        location_area_id=LocationAreaId(location_area_id),
        establishment_type=(
            None if establishment_type is None else EstablishmentType(establishment_type)
        ),
        establishment_id=establishment_id,
    )


__all__ = ["build_location_establishment"]
