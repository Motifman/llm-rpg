import pytest
from ai_rpg_world.domain.skill.service.skill_to_hitbox_service import SkillToHitBoxDomainService
from ai_rpg_world.domain.skill.value_object.skill_hit_pattern import SkillHitPattern, SkillHitTimelineSegment
from ai_rpg_world.domain.skill.enum.skill_enum import SkillHitPatternType
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape, RelativeCoordinate
from ai_rpg_world.domain.combat.value_object.hit_box_velocity import HitBoxVelocity
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.common.value_object import WorldTick

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
