import math

import pytest

from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape, RelativeCoordinate
from ai_rpg_world.domain.combat.value_object.hit_box_velocity import HitBoxVelocity
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.skill.enum.skill_enum import SkillHitPatternType
from ai_rpg_world.domain.skill.exception.skill_exceptions import SkillRotationAngleUnsupportedException
from ai_rpg_world.domain.skill.service.skill_to_hitbox_service import SkillToHitBoxDomainService
from ai_rpg_world.domain.skill.value_object.skill_hit_pattern import SkillHitPattern, SkillHitTimelineSegment
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.facing import Facing


class TestSkillToHitBoxDomainService:
    @pytest.fixture
    def service(self):
        return SkillToHitBoxDomainService()

    class TestRotation:
        def test_rotate_relative_coordinate(self, service):
            rel = RelativeCoordinate(0, 1, 0) # SOUTH (Forward)
            assert service._rotate_relative_coordinate(rel, DirectionEnum.SOUTH) == RelativeCoordinate(0, 1, 0)
            assert service._rotate_relative_coordinate(rel, DirectionEnum.NORTH) == RelativeCoordinate(0, -1, 0)
            assert service._rotate_relative_coordinate(rel, DirectionEnum.EAST) == RelativeCoordinate(1, 0, 0)
            assert service._rotate_relative_coordinate(rel, DirectionEnum.WEST) == RelativeCoordinate(-1, 0, 0)

        def test_rotate_velocity(self, service):
            vel = HitBoxVelocity(0, 1, 0)
            assert service._rotate_velocity(vel, DirectionEnum.SOUTH) == HitBoxVelocity(0, 1, 0)
            assert service._rotate_velocity(vel, DirectionEnum.NORTH) == HitBoxVelocity(0, -1, 0)
            assert service._rotate_velocity(vel, DirectionEnum.EAST) == HitBoxVelocity(1, 0, 0)
            assert service._rotate_velocity(vel, DirectionEnum.WEST) == HitBoxVelocity(-1, 0, 0)

        def test_diagonal_velocity_keeps_its_magnitude_as_floats(self, service):
            """速度を斜め方向へ回すと成分は小数のまま残り、速さが軸方向と等しく保たれる。"""
            vel = HitBoxVelocity(0, 1, 0)

            rotated = service._rotate_velocity(vel, DirectionEnum.SOUTHEAST)

            half_sqrt2 = math.sqrt(2) / 2
            assert rotated.dx == pytest.approx(half_sqrt2)
            assert rotated.dy == pytest.approx(half_sqrt2)
            assert math.hypot(rotated.dx, rotated.dy) == pytest.approx(1.0)

        def test_axis_rotation_leaves_exactly_zero_on_the_unused_axis(self, service):
            """速度を軸方向へ回すと、動かない軸の成分は誤差を含まない 0.0 になる。"""
            vel = HitBoxVelocity(0, 1, 0)

            rotated = service._rotate_velocity(vel, DirectionEnum.NORTH)

            assert rotated.dx == 0.0
            assert rotated.dy == -1.0

        def test_fractional_velocity_survives_rotation(self, service):
            """1 ティックに 1 マス未満しか進まない速度を回しても、小数部分が丸められない。"""
            vel = HitBoxVelocity(0, 0.25, 0)

            rotated = service._rotate_velocity(vel, DirectionEnum.EAST)

            assert rotated.dx == pytest.approx(0.25)
            assert rotated.dy == pytest.approx(0.0)

        def test_diagonal_coordinate_still_snaps_to_a_grid_cell(self, service):
            """座標を斜め方向へ回した結果は、速度と違って整数のマス目に載る。"""
            rel = RelativeCoordinate(0, 1, 0)

            rotated = service._rotate_relative_coordinate(rel, DirectionEnum.SOUTHEAST)

            assert rotated == RelativeCoordinate(1, 1, 0)

        def test_unsupported_rotation_angle_raises(self, service, monkeypatch):
            """cos/sin の表に無い回転角を渡されると、黙って回さずに例外を投げる。"""
            monkeypatch.setattr(Facing, "rotation_from_south_degrees", lambda self: 30.0)

            with pytest.raises(SkillRotationAngleUnsupportedException):
                service._rotate_velocity(HitBoxVelocity(0, 1, 0), DirectionEnum.EAST)

        def test_rotate_complex_shape(self, service):
            # L字型の形状 (SOUTH向き時)
            # (0,0), (0,1), (1,1)
            shape = HitBoxShape([
                RelativeCoordinate(0, 0, 0),
                RelativeCoordinate(0, 1, 0),
                RelativeCoordinate(1, 1, 0)
            ])
            
            # NORTH向きに回転 (-rel.dx, -rel.dy)
            # (0,0), (0,-1), (-1,-1)
            rotated_n = service._rotate_shape(shape, DirectionEnum.NORTH)
            assert RelativeCoordinate(0, 0, 0) in rotated_n.relative_coordinates
            assert RelativeCoordinate(0, -1, 0) in rotated_n.relative_coordinates
            assert RelativeCoordinate(-1, -1, 0) in rotated_n.relative_coordinates
            
            # EAST向きに回転 (rel.dy, -rel.dx)
            # (0,0), (1,0), (1,-1)
            rotated_e = service._rotate_shape(shape, DirectionEnum.EAST)
            assert RelativeCoordinate(0, 0, 0) in rotated_e.relative_coordinates
            assert RelativeCoordinate(1, 0, 0) in rotated_e.relative_coordinates
            assert RelativeCoordinate(1, -1, 0) in rotated_e.relative_coordinates

    class TestCalculateSpawnParams:
        def test_multi_segment_with_offsets(self, service):
            pattern = SkillHitPattern(
                pattern_type=SkillHitPatternType.MELEE,
                timeline_segments=(
                    SkillHitTimelineSegment(0, 5, HitBoxShape.single_cell(), spawn_offset=RelativeCoordinate(0, 1, 0)),
                    SkillHitTimelineSegment(10, 5, HitBoxShape.single_cell(), spawn_offset=RelativeCoordinate(0, 2, 0))
                )
            )
            
            origin = Coordinate(10, 10, 0)
            params = service.calculate_spawn_params(pattern, origin, DirectionEnum.EAST, WorldTick(100), 1.5)

            assert len(params) == 2
            assert params[0].initial_coordinate == Coordinate(11, 10, 0)
            assert params[0].activation_tick == 100
            assert params[1].initial_coordinate == Coordinate(12, 10, 0)
            assert params[1].activation_tick == 110

        def test_respects_base_power_multiplier(self, service):
            pattern = SkillHitPattern(
                pattern_type=SkillHitPatternType.MELEE,
                timeline_segments=(
                    SkillHitTimelineSegment(0, 5, HitBoxShape.single_cell(), segment_power_multiplier=2.0),
                )
            )
            params = service.calculate_spawn_params(pattern, Coordinate(0,0,0), DirectionEnum.SOUTH, WorldTick(0), 1.5)
            assert params[0].power_multiplier == 3.0 # 1.5 * 2.0
