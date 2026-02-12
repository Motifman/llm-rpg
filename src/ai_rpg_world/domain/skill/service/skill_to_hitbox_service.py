from typing import List
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape, RelativeCoordinate
from ai_rpg_world.domain.combat.value_object.hit_box_velocity import HitBoxVelocity
from ai_rpg_world.domain.combat.value_object.hit_box_spawn_param import HitBoxSpawnParam
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.skill.value_object.skill_hit_pattern import SkillHitPattern, SkillHitTimelineSegment
from ai_rpg_world.domain.common.value_object import WorldTick


class SkillToHitBoxDomainService:
    """
    スキルのヒットパターンを、指定された向きに応じたヒットボックス設定に変換するドメインサービス。
    """

    def calculate_spawn_params(
        self,
        hit_pattern: SkillHitPattern,
        origin: Coordinate,
        direction: DirectionEnum,
        start_tick: WorldTick,
        base_power_multiplier: float,
        attacker_stats: BaseStats | None = None,
    ) -> List[HitBoxSpawnParam]:
        """
        スキルのヒットパターンと、使用者の位置・向きから、生成すべき全ヒットボックスのパラメータを計算する。
        """
        params = []
        for segment in hit_pattern.timeline_segments:
            # 1. 形状の回転
            rotated_shape = self._rotate_shape(segment.shape, direction)

            # 2. 速度の回転
            rotated_velocity = self._rotate_velocity(segment.velocity, direction)

            # 3. 出現オフセットの回転
            rotated_offset = self._rotate_relative_offset(segment.spawn_offset, direction)
            initial_coordinate = Coordinate(
                origin.x + rotated_offset.dx,
                origin.y + rotated_offset.dy,
                origin.z + rotated_offset.dz
            )

            # 4. 有効化タイミングの計算
            activation_tick = start_tick.value + segment.start_offset_ticks

            # 5. 最終的な威力倍率の計算
            total_power_multiplier = base_power_multiplier * segment.segment_power_multiplier

            params.append(HitBoxSpawnParam(
                shape=rotated_shape,
                velocity=rotated_velocity,
                initial_coordinate=initial_coordinate,
                activation_tick=activation_tick,
                duration_ticks=segment.duration_ticks,
                power_multiplier=total_power_multiplier,
                attacker_stats=attacker_stats
            ))
        
        return params

    def _rotate_shape(self, shape: HitBoxShape, direction: DirectionEnum) -> HitBoxShape:
        rotated_rel_coords = [
            self._rotate_relative_coordinate(rel, direction)
            for rel in shape.relative_coordinates
        ]
        return HitBoxShape(rotated_rel_coords)

    def _rotate_relative_coordinate(self, rel: RelativeCoordinate, direction: DirectionEnum) -> RelativeCoordinate:
        # スキル定義は SOUTH (dx=0, dy=1) を前方としていると仮定
        if direction == DirectionEnum.SOUTH:
            return rel
        elif direction == DirectionEnum.NORTH:
            return RelativeCoordinate(-rel.dx, -rel.dy, rel.dz)
        elif direction == DirectionEnum.EAST:
            # (x, y) -> (y, -x)  ※SOUTH(0,1) -> EAST(1,0) になるための変換
            return RelativeCoordinate(rel.dy, -rel.dx, rel.dz)
        elif direction == DirectionEnum.WEST:
            # (x, y) -> (-y, x)
            return RelativeCoordinate(-rel.dy, rel.dx, rel.dz)
        return rel

    def _rotate_velocity(self, vel: HitBoxVelocity, direction: DirectionEnum) -> HitBoxVelocity:
        if direction == DirectionEnum.SOUTH:
            return vel
        elif direction == DirectionEnum.NORTH:
            return HitBoxVelocity(-vel.dx, -vel.dy, vel.dz)
        elif direction == DirectionEnum.EAST:
            return HitBoxVelocity(vel.dy, -vel.dx, vel.dz)
        elif direction == DirectionEnum.WEST:
            return HitBoxVelocity(-vel.dy, vel.dx, vel.dz)
        return vel

    def _rotate_relative_offset(self, offset: RelativeCoordinate, direction: DirectionEnum) -> RelativeCoordinate:
        return self._rotate_relative_coordinate(offset, direction)
