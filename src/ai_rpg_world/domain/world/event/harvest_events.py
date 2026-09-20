from dataclasses import dataclass

from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


@dataclass(frozen=True)
class HarvestStartedEvent(BaseDomainEvent[WorldObjectId, str]):
    """採取アクションが開始された際のイベント"""
    actor_id: WorldObjectId
    target_id: WorldObjectId
    finish_tick: WorldTick

    @classmethod
    # 基底の create は **kwargs を受けるので、名前付き引数へ狭めた上書きは
    # 原理的に非互換になる。狭めているのは、このイベントが必要とする値を
    # 呼び出し側で検査させるため。
    def create(  # type: ignore[override]
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
    # 基底の create は **kwargs を受けるので、名前付き引数へ狭めた上書きは
    # 原理的に非互換になる。狭めているのは、このイベントが必要とする値を
    # 呼び出し側で検査させるため。
    def create(  # type: ignore[override]
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
    loot_table_id: LootTableId

    @classmethod
    # 基底の create は **kwargs を受けるので、名前付き引数へ狭めた上書きは
    # 原理的に非互換になる。狭めているのは、このイベントが必要とする値を
    # 呼び出し側で検査させるため。
    def create(  # type: ignore[override]
        cls,
        aggregate_id: WorldObjectId,
        aggregate_type: str,
        actor_id: WorldObjectId,
        target_id: WorldObjectId,
        loot_table_id: LootTableId
    ) -> "HarvestCompletedEvent":
        return super().create(
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            actor_id=actor_id,
            target_id=target_id,
            loot_table_id=loot_table_id
        )
