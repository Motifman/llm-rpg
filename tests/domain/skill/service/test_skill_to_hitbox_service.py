import math

import pytest

from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape, RelativeCoordinate
from ai_rpg_world.domain.combat.value_object.hit_box_velocity import HitBoxVelocity
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
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
        @pytest.mark.parametrize("direction, speed, expected_cell, expected_velocity", [
            (DirectionEnum.SOUTH, 1, (0, 1, 0), (0, 1, 0)),
            (DirectionEnum.NORTH, 1, (0, -1, 0), (0, -1, 0)),
            (DirectionEnum.EAST, 1, (1, 0, 0), (1, 0, 0)),
            (DirectionEnum.WEST, 1, (-1, 0, 0), (-1, 0, 0)),
            (DirectionEnum.EAST, 0.25, (1, 0, 0), (0.25, 0, 0)),
            (DirectionEnum.UP, 1, (0, 1, 0), (0, 1, 0)),
            (DirectionEnum.DOWN, 1, (0, 1, 0), (0, 1, 0)),
        ])
        def test_spawn_params_rotate_axis_shapes_and_velocities(
            self, service, direction, speed, expected_cell, expected_velocity,
        ):
            """生成される形状と速度は方位へ回り、小数速度と軸の厳密なゼロを保つ。"""
            pattern = SkillHitPattern.projectile(
                HitBoxShape([RelativeCoordinate(0, 1, 0)]), HitBoxVelocity(0, speed, 0), 5,
            )

            params = service.calculate_spawn_params(
                pattern, Coordinate(10, 10), direction, WorldTick(0), 1.0,
            )

            assert len(params) == 1
            assert params[0].shape.relative_coordinates == [RelativeCoordinate(*expected_cell)]
            assert params[0].velocity == HitBoxVelocity(*expected_velocity)

        def test_diagonal_spawn_snaps_shape_but_preserves_velocity_magnitude(self, service):
            """斜めの生成形状は整数マスへ丸め、速度は小数のまま速さ1を保つ。"""
            pattern = SkillHitPattern.projectile(
                HitBoxShape([RelativeCoordinate(0, 1, 0)]), HitBoxVelocity(0, 1, 0), 5,
            )

            params = service.calculate_spawn_params(
                pattern, Coordinate(10, 10), DirectionEnum.SOUTHEAST, WorldTick(0), 1.0,
            )

            assert len(params) == 1
            assert params[0].shape.relative_coordinates == [RelativeCoordinate(1, 1, 0)]
            half_sqrt2 = math.sqrt(2) / 2
            assert params[0].velocity.dx == pytest.approx(half_sqrt2)
            assert params[0].velocity.dy == pytest.approx(half_sqrt2)
            assert math.hypot(params[0].velocity.dx, params[0].velocity.dy) == pytest.approx(1.0)

        def test_rotating_by_a_direction_without_a_planar_angle_raises(self, service):
            """回転角を持たない向きを回転に渡すと、0 度扱いにせず例外を投げる。"""
            with pytest.raises(SkillRotationAngleUnsupportedException):
                service._rotate_xy_precise(0.0, 1.0, DirectionEnum.UP)

        def test_unsupported_rotation_angle_raises(self, service, monkeypatch):
            """cos/sin の表に無い回転角を渡されると、黙って回さずに例外を投げる。"""
            monkeypatch.setattr(Facing, "rotation_from_south_degrees", lambda self: 30.0)

            with pytest.raises(SkillRotationAngleUnsupportedException):
                service._rotate_velocity(HitBoxVelocity(0, 1, 0), DirectionEnum.EAST)

        @pytest.mark.parametrize("direction, expected_cells", [
            (DirectionEnum.NORTH, [(0, 0, 0), (0, -1, 0), (-1, -1, 0)]),
            (DirectionEnum.EAST, [(0, 0, 0), (1, 0, 0), (1, -1, 0)]),
        ])
        def test_spawn_params_rotate_exactly_the_complex_shape(self, service, direction, expected_cells):
            """L字の3マスを回転して生成し、余分な攻撃マスを混ぜない。"""
            pattern = SkillHitPattern.single_pulse(SkillHitPatternType.MELEE, HitBoxShape([
                RelativeCoordinate(0, 0, 0), RelativeCoordinate(0, 1, 0), RelativeCoordinate(1, 1, 0),
            ]))

            params = service.calculate_spawn_params(
                pattern, Coordinate(10, 10), direction, WorldTick(0), 1.0,
            )

            assert len(params) == 1
            cells = params[0].shape.relative_coordinates
            assert len(cells) == 3
            assert set(cells) == {RelativeCoordinate(*cell) for cell in expected_cells}

    class TestCalculateSpawnParams:
        @pytest.mark.parametrize("durations, attacker_stats", [
            ((5, 5), None),
            ((3, 7), BaseStats(120, 80, 17, 13, 11, 0.1, 0.2)),
        ], ids=["original-segments", "distinct-durations-and-stats"])
        def test_multi_segment_with_offsets(self, service, durations, attacker_stats):
            """区間ごとの位置・発動時刻・継続期間と攻撃者の能力値を生成結果へ渡す。"""
            pattern = SkillHitPattern(
                pattern_type=SkillHitPatternType.MELEE,
                timeline_segments=(
                    SkillHitTimelineSegment(0, durations[0], HitBoxShape.single_cell(), spawn_offset=RelativeCoordinate(0, 1, 0)),
                    SkillHitTimelineSegment(10, durations[1], HitBoxShape.single_cell(), spawn_offset=RelativeCoordinate(0, 2, 0))
                )
            )
            
            origin = Coordinate(10, 10, 0)
            params = service.calculate_spawn_params(
                pattern, origin, DirectionEnum.EAST, WorldTick(100), 1.5, attacker_stats=attacker_stats,
            )

            assert len(params) == 2
            assert params[0].initial_coordinate == Coordinate(11, 10, 0)
            assert params[0].activation_tick == 100
            assert params[1].initial_coordinate == Coordinate(12, 10, 0)
            assert params[1].activation_tick == 110
            assert [param.duration_ticks for param in params] == list(durations)
            assert [param.attacker_stats for param in params] == [attacker_stats, attacker_stats]

        def test_respects_base_power_multiplier(self, service):
            pattern = SkillHitPattern(
                pattern_type=SkillHitPatternType.MELEE,
                timeline_segments=(
                    SkillHitTimelineSegment(0, 5, HitBoxShape.single_cell(), segment_power_multiplier=2.0),
                )
            )
            params = service.calculate_spawn_params(pattern, Coordinate(0,0,0), DirectionEnum.SOUTH, WorldTick(0), 1.5)
            assert params[0].power_multiplier == 3.0 # 1.5 * 2.0
