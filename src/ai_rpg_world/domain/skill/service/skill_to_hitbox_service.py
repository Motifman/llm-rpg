import math
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
        if direction in {DirectionEnum.UP, DirectionEnum.DOWN}:
            return rel
        rotated_dx, rotated_dy = self._rotate_xy(rel.dx, rel.dy, direction)
        return RelativeCoordinate(rotated_dx, rotated_dy, rel.dz)

    def _rotate_velocity(self, vel: HitBoxVelocity, direction: DirectionEnum) -> HitBoxVelocity:
        if direction in {DirectionEnum.UP, DirectionEnum.DOWN}:
            return vel
        rotated_dx, rotated_dy = self._rotate_xy(vel.dx, vel.dy, direction)
        return HitBoxVelocity(rotated_dx, rotated_dy, vel.dz)

    def _rotate_relative_offset(self, offset: RelativeCoordinate, direction: DirectionEnum) -> RelativeCoordinate:
        return self._rotate_relative_coordinate(offset, direction)

    def _rotate_xy(self, dx: int, dy: int, direction: DirectionEnum) -> tuple[int, int]:
        """SOUTH を基準としたローカル座標を指定方向へ回転する。"""
        angles = {
            DirectionEnum.SOUTH: 0.0,
            DirectionEnum.SOUTHEAST: -45.0,
            DirectionEnum.EAST: -90.0,
            DirectionEnum.NORTHEAST: -135.0,
            DirectionEnum.NORTH: 180.0,
            DirectionEnum.NORTHWEST: 135.0,
            DirectionEnum.WEST: 90.0,
            DirectionEnum.SOUTHWEST: 45.0,
        }
        angle = math.radians(angles.get(direction, 0.0))
        rotated_x = dx * math.cos(angle) - dy * math.sin(angle)
        rotated_y = dx * math.sin(angle) + dy * math.cos(angle)
        return int(round(rotated_x)), int(round(rotated_y))
