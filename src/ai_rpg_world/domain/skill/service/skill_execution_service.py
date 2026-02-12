from typing import List, Optional
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.skill.service.skill_targeting_service import SkillTargetingDomainService
from ai_rpg_world.domain.skill.service.skill_to_hitbox_service import SkillToHitBoxDomainService, HitBoxSpawnParam


class SkillExecutionDomainService:
    """
    スキルの実行プロセス（ターゲティング、リソース消費、クールダウン開始、ヒットボックス生成パラメータ計算）
    を統括するドメインサービス。
    """
    def __init__(
        self,
        targeting_service: SkillTargetingDomainService,
        to_hitbox_service: SkillToHitBoxDomainService,
    ):
        self._targeting_service = targeting_service
        self._to_hitbox_service = to_hitbox_service

    def execute_skill(
        self,
        physical_map: PhysicalMapAggregate,
        player_status: PlayerStatusAggregate,
        skill_loadout: SkillLoadoutAggregate,
        skill_spec: SkillSpec,
        slot_index: int,
        current_tick: int,
        auto_aim: bool = False,
        target_direction_override: Optional[DirectionEnum] = None,
    ) -> List[HitBoxSpawnParam]:
        """
        スキルを実行し、消費リソースの反映とヒットボックス生成パラメータのリストを返す。
        """
        actor_id = WorldObjectId(player_status.player_id.value)
        actor = physical_map.get_actor(actor_id)

        # 1. 射撃方向の決定
        target_direction = None
        if auto_aim:
            target_direction = self._targeting_service.calculate_auto_aim_direction(
                physical_map=physical_map,
                actor_id=actor_id
            )
        
        if not target_direction and target_direction_override:
            target_direction = target_direction_override
        
        if not target_direction:
            # オートエイムで見つからず、上書き指定もない場合は現在の向きを使用
            target_direction = actor.direction or DirectionEnum.SOUTH

        # 向きを更新（スキルを放つ方向を向く）
        actor.turn(target_direction)

        # 2. リソース消費 (バリデーション含む)
        player_status.consume_resources(
            mp_cost=skill_spec.mp_cost or 0,
            stamina_cost=skill_spec.stamina_cost or 0,
            hp_cost=skill_spec.hp_cost or 0,
        )
        
        # 3. クールダウン開始
        skill_loadout.use_skill(
            slot_index=slot_index,
            current_tick=current_tick,
            actor_id=player_status.player_id.value,
        )

        # 4. ヒットボックス生成パラメータ計算
        return self._to_hitbox_service.calculate_spawn_params(
            hit_pattern=skill_spec.hit_pattern,
            origin=actor.coordinate,
            direction=target_direction,
            start_tick=WorldTick(current_tick),
            base_power_multiplier=skill_spec.power_multiplier,
            attacker_stats=player_status.get_effective_stats(WorldTick(current_tick))
        )
