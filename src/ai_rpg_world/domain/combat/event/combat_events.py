from dataclasses import dataclass
from typing import TYPE_CHECKING

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId

if TYPE_CHECKING:
    from ai_rpg_world.domain.world.value_object.spot_id import SpotId


@dataclass(frozen=True)
class HitBoxCreatedEvent(BaseDomainEvent[HitBoxId, "HitBoxAggregate"]):
    """HitBox生成イベント"""
    spot_id: "SpotId"
    owner_id: WorldObjectId
    initial_coordinate: Coordinate
    duration: int
    power_multiplier: float
    shape_cell_count: int
    effect_count: int


@dataclass(frozen=True)
class HitBoxMovedEvent(BaseDomainEvent[HitBoxId, "HitBoxAggregate"]):
    """HitBox移動イベント"""
    from_coordinate: Coordinate
    to_coordinate: Coordinate


@dataclass(frozen=True)
class HitBoxHitRecordedEvent(BaseDomainEvent[HitBoxId, "HitBoxAggregate"]):
    """HitBoxヒット記録イベント"""
    owner_id: WorldObjectId
    target_id: WorldObjectId
    hit_coordinate: Coordinate


@dataclass(frozen=True)
class HitBoxDeactivatedEvent(BaseDomainEvent[HitBoxId, "HitBoxAggregate"]):
    """HitBox無効化イベント"""
    reason: str


@dataclass(frozen=True)
class HitBoxObstacleCollidedEvent(BaseDomainEvent[HitBoxId, "HitBoxAggregate"]):
    """HitBox障害物衝突イベント"""
    collision_coordinate: Coordinate
    obstacle_collision_policy: str
