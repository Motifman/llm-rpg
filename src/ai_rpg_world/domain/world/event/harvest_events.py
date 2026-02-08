from dataclasses import dataclass
from typing import Optional, Any, Dict
from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.common.value_object import WorldTick


@dataclass(frozen=True)
class HarvestStartedEvent(BaseDomainEvent[WorldObjectId, str]):
    """採取アクションが開始された際のイベント"""
    actor_id: WorldObjectId
    target_id: WorldObjectId
    finish_tick: WorldTick

    @classmethod
    def create(
        cls,
        aggregate_id: WorldObjectId,
        aggregate_type: str,
        actor_id: WorldObjectId,
        target_id: WorldObjectId,
        finish_tick: WorldTick
    ) -> "HarvestStartedEvent":
        return super().create(
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            actor_id=actor_id,
            target_id=target_id,
            finish_tick=finish_tick
        )


@dataclass(frozen=True)
class HarvestCancelledEvent(BaseDomainEvent[WorldObjectId, str]):
    """採取アクションが中断された際のイベント"""
    actor_id: WorldObjectId
    target_id: WorldObjectId
    reason: str

    @classmethod
    def create(
        cls,
        aggregate_id: WorldObjectId,
        aggregate_type: str,
        actor_id: WorldObjectId,
        target_id: WorldObjectId,
        reason: str
    ) -> "HarvestCancelledEvent":
        return super().create(
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            actor_id=actor_id,
            target_id=target_id,
            reason=reason
        )


@dataclass(frozen=True)
class HarvestCompletedEvent(BaseDomainEvent[WorldObjectId, str]):
    """採取アクションが完了した際のイベント"""
    actor_id: WorldObjectId
    target_id: WorldObjectId
    loot_table_id: str

    @classmethod
    def create(
        cls,
        aggregate_id: WorldObjectId,
        aggregate_type: str,
        actor_id: WorldObjectId,
        target_id: WorldObjectId,
        loot_table_id: str
    ) -> "HarvestCompletedEvent":
        return super().create(
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            actor_id=actor_id,
            target_id=target_id,
            loot_table_id=loot_table_id
        )
