from dataclasses import dataclass

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


@dataclass(frozen=True)
class HitBoxCreatedEvent(BaseDomainEvent[HitBoxId, "HitBoxAggregate"]):
    """HitBox生成イベント"""
    owner_id: WorldObjectId
    initial_coordinate: Coordinate
    duration: int
    power_multiplier: float
    shape_cell_count: int


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
