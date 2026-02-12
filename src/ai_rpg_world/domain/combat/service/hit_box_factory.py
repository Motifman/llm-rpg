from typing import List, Optional

from ai_rpg_world.domain.combat.aggregate.hit_box_aggregate import HitBoxAggregate
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.combat.value_object.hit_box_spawn_param import HitBoxSpawnParam
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.common.value_object import WorldTick


class HitBoxFactory:
    """
    HitBoxAggregateを生成するためのドメインファクトリ。
    複雑な生成ロジックや、パラメータセット（HitBoxSpawnParam）からの生成をカプセル化する。
    """

    @staticmethod
    def create_from_params(
        hit_box_ids: List[HitBoxId],
        params: List[HitBoxSpawnParam],
        spot_id: SpotId,
        owner_id: WorldObjectId,
        start_tick: WorldTick,
        skill_id: Optional[str] = None
    ) -> List[HitBoxAggregate]:
        """
        HitBoxSpawnParamのリストからHitBoxAggregateのリストを生成する。
        
        Args:
            hit_box_ids: 生成するHitBoxに使用するIDのリスト（外部で採番済みであることを想定）
            params: 生成パラメータのリスト
            spot_id: 配置先のスポットID
            owner_id: 所有者のオブジェクトID
            start_tick: 生成開始時のワールドティック
            skill_id: 関連するスキルID（任意）
            
        Returns:
            List[HitBoxAggregate]: 生成された集約のリスト
        """
        if len(hit_box_ids) < len(params):
            raise ValueError(f"Not enough hit_box_ids provided. required: {len(params)}, provided: {len(hit_box_ids)}")

        hit_boxes = []
        for i, param in enumerate(params):
            hit_box = HitBoxAggregate.create(
                hit_box_id=hit_box_ids[i],
                spot_id=spot_id,
                owner_id=owner_id,
                shape=param.shape,
                initial_coordinate=param.initial_coordinate,
                start_tick=start_tick,
                duration=param.duration_ticks,
                power_multiplier=param.power_multiplier,
                velocity=param.velocity,
                attacker_stats=param.attacker_stats,
                activation_tick=param.activation_tick,
                skill_id=skill_id
            )
            hit_boxes.append(hit_box)
            
        return hit_boxes
