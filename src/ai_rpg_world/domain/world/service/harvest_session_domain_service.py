"""HarvestSessionDomainService: 採取セッション（開始・完了・キャンセル）のオーケストレーションを行うドメインサービス。

リポジトリに依存せず、渡された actor と target を直接更新する。
PhysicalMapAggregate からの責務分離により、採取の流れを集約する。
"""

from typing import Optional

from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import HarvestableComponent
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.service.harvest_session_policy import HarvestSessionPolicy
from ai_rpg_world.domain.world.event.harvest_events import (
    HarvestStartedEvent,
    HarvestCompletedEvent,
    HarvestCancelledEvent,
)


class HarvestSessionDomainService:
    """
    採取セッションの開始・完了・キャンセルのオーケストレーションを行うドメインサービス。
    リポジトリ非依存。渡された actor, target を直接更新する。
    """

    @staticmethod
    def start_harvest(
        actor: WorldObject,
        target: WorldObject,
        current_tick: WorldTick,
    ) -> HarvestStartedEvent:
        """
        採取を開始する。検証・コンポーネント呼び出し・アクターのビジー設定・イベント作成を行う。
        """
        HarvestSessionPolicy.validate_can_start_harvest(actor, target, current_tick)
        finish_tick = target.component.start_harvest(actor.object_id, current_tick)
        actor.set_busy(finish_tick)
        return HarvestStartedEvent.create(
            aggregate_id=target.object_id,
            aggregate_type="WorldObject",
            actor_id=actor.object_id,
            target_id=target.object_id,
            finish_tick=finish_tick,
        )

    @staticmethod
    def finish_harvest(
        actor: WorldObject,
        target: WorldObject,
        current_tick: WorldTick,
    ) -> Optional[HarvestCompletedEvent]:
        """
        採取を完了する。検証・コンポーネント呼び出し・アクターのビジー解除・イベント作成を行う。
        まだ完了していない場合は None を返す（イベントは発行しない）。
        """
        HarvestSessionPolicy.validate_is_harvestable(target)
        success = target.component.finish_harvest(actor.object_id, current_tick)
        if success:
            actor.clear_busy()
            loot_table_id = target.component.loot_table_id
            return HarvestCompletedEvent.create(
                aggregate_id=target.object_id,
                aggregate_type="WorldObject",
                actor_id=actor.object_id,
                target_id=target.object_id,
                loot_table_id=loot_table_id,
            )
        return None

    @staticmethod
    def cancel_harvest(
        actor: WorldObject,
        target: WorldObject,
        reason: str = "cancelled",
    ) -> HarvestCancelledEvent:
        """
        採取を中断する。検証・コンポーネント呼び出し・アクターのビジー解除・イベント作成を行う。
        """
        HarvestSessionPolicy.validate_is_harvestable(target)
        target.component.cancel_harvest(actor.object_id)
        actor.clear_busy()
        return HarvestCancelledEvent.create(
            aggregate_id=target.object_id,
            aggregate_type="WorldObject",
            actor_id=actor.object_id,
            target_id=target.object_id,
            reason=reason,
        )
