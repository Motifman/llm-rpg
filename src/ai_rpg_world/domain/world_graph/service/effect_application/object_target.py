from __future__ import annotations

from typing import Any, Optional

from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.entity.spot_object import SpotObject
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId


def spot_object_id_from_param(val: Any) -> SpotObjectId:
    if isinstance(val, SpotObjectId):
        return val
    return SpotObjectId.create(val)


def sub_location_id_from_param(val: Any) -> SubLocationId:
    if isinstance(val, SubLocationId):
        return val
    return SubLocationId.create(val)


def resolve_target_object(
    interior: SpotInterior,
    acting_object: SpotObject | None,
    params: dict[str, Any],
) -> SpotObject | None:
    target_raw = params.get("object_id")
    if target_raw is None:
        return acting_object
    target_id = spot_object_id_from_param(target_raw)
    target = interior.get_object(target_id)
    return target or acting_object
