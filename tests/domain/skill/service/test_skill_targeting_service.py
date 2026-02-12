import pytest
from ai_rpg_world.domain.skill.service.skill_targeting_service import SkillTargetingDomainService
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum, ObjectTypeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

class TestSkillTargetingDomainService:
    @pytest.fixture
    def service(self):
        return SkillTargetingDomainService()

    @pytest.fixture
    def simple_map(self):
        tiles = [Tile(Coordinate(x, y, 0), TerrainType.road()) for x in range(20) for y in range(20)]
        return PhysicalMapAggregate.create(SpotId(1), tiles)

    def _create_actor(self, actor_id, coord, direction=DirectionEnum.SOUTH):
        comp = ActorComponent(direction=direction, player_id=PlayerId(actor_id))
        return WorldObject(WorldObjectId(actor_id), coord, ObjectTypeEnum.PLAYER, component=comp)

    class TestCalculateAutoAimDirection:
        def test_finds_nearest_enemy(self, service, simple_map):
            outer = TestSkillTargetingDomainService()
            actor_id = 1
            actor_coord = Coordinate(5, 5)
            simple_map.add_object(outer._create_actor(actor_id, actor_coord))
            
            # 2つの敵: 1つは距離2 (7,5)、もう1つは距離3 (5,8)
            enemy1_id = 101
            enemy2_id = 102
            simple_map.add_object(outer._create_actor(enemy1_id, Coordinate(7, 5))) # EAST
            simple_map.add_object(outer._create_actor(enemy2_id, Coordinate(5, 8))) # SOUTH
            
            direction = service.calculate_auto_aim_direction(simple_map, WorldObjectId(actor_id))
            assert direction == DirectionEnum.EAST

        def test_respects_vision_range(self, service, simple_map):
            outer = TestSkillTargetingDomainService()
            actor_id = 1
            simple_map.add_object(outer._create_actor(actor_id, Coordinate(5, 5)))
            
            # 敵が範囲外 (16, 5) -> 距離 11
            simple_map.add_object(outer._create_actor(101, Coordinate(16, 5)))
            
            # デフォルト(10)では見つからない
            direction = service.calculate_auto_aim_direction(simple_map, WorldObjectId(actor_id))
            assert direction is None
            
            # 範囲を11に広げれば見つかる
            direction = service.calculate_auto_aim_direction(simple_map, WorldObjectId(actor_id), vision_range=11)
            assert direction == DirectionEnum.EAST

        def test_blocked_by_wall_returns_none(self, service, simple_map):
            outer = TestSkillTargetingDomainService()
            actor_id = 1
            actor_coord = Coordinate(5, 5)
            simple_map.add_object(outer._create_actor(actor_id, actor_coord))
            
            # 敵(7,5)の間に壁(6,5)を設置
            enemy_id = 101
            simple_map.add_object(outer._create_actor(enemy_id, Coordinate(7, 5)))
            simple_map.change_tile_terrain(Coordinate(6, 5), TerrainType.wall())
            
            # 壁で視線が遮られるので見つからないはず
            direction = service.calculate_auto_aim_direction(simple_map, WorldObjectId(actor_id))
            assert direction is None

        def test_no_enemies_returns_none(self, service, simple_map):
            outer = TestSkillTargetingDomainService()
            actor_id = 1
            simple_map.add_object(outer._create_actor(actor_id, Coordinate(5, 5)))
            
            # 非アクターのオブジェクト（宝箱など）は無視される
            chest = WorldObject(WorldObjectId(101), Coordinate(6, 5), ObjectTypeEnum.CHEST)
            simple_map.add_object(chest)
            
            direction = service.calculate_auto_aim_direction(simple_map, WorldObjectId(actor_id))
            assert direction is None

    class TestCalculateGeneralDirection:
        @pytest.mark.parametrize("to_coord, expected", [
            (Coordinate(7, 5), DirectionEnum.EAST),
            (Coordinate(3, 5), DirectionEnum.WEST),
            (Coordinate(5, 7), DirectionEnum.SOUTH),
            (Coordinate(5, 3), DirectionEnum.NORTH),
            # 斜め: xの差が大きい場合は左右優先
            (Coordinate(7, 6), DirectionEnum.EAST), # dx=2, dy=1
            (Coordinate(6, 8), DirectionEnum.SOUTH), # dx=1, dy=3
            # 同じ座標
            (Coordinate(5, 5), DirectionEnum.SOUTH),
        ])
        def test_directions(self, service, to_coord, expected):
            from_coord = Coordinate(5, 5)
            assert service._calculate_general_direction(from_coord, to_coord) == expected
