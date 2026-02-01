from dataclasses import dataclass
from typing import Optional
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.enum.world_enum import BehaviorStateEnum


@dataclass(frozen=True)
class ActorStateChangedEvent(BaseDomainEvent[WorldObjectId, str]):
    """アクターの行動状態が変化したイベント"""
    actor_id: WorldObjectId
    old_state: BehaviorStateEnum
    new_state: BehaviorStateEnum


@dataclass(frozen=True)
class TargetSpottedEvent(BaseDomainEvent[WorldObjectId, str]):
    """ターゲットを視認したイベント"""
    actor_id: WorldObjectId
    target_id: WorldObjectId
    coordinate: Coordinate


@dataclass(frozen=True)
class TargetLostEvent(BaseDomainEvent[WorldObjectId, str]):
    """ターゲットを見失ったイベント"""
    actor_id: WorldObjectId
    target_id: WorldObjectId
    last_known_coordinate: Coordinate


@dataclass(frozen=True)
class BehaviorStuckEvent(BaseDomainEvent[WorldObjectId, str]):
    """行動がスタック（移動失敗の連続）したイベント"""
    actor_id: WorldObjectId
    state: BehaviorStateEnum
    coordinate: Coordinate
