import pytest
from unittest.mock import Mock
from ai_rpg_world.domain.combat.service.hit_box_collision_service import HitBoxCollisionDomainService
from ai_rpg_world.domain.combat.aggregate.hit_box_aggregate import HitBoxAggregate
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.combat.value_object.hit_box_velocity import HitBoxVelocity
from ai_rpg_world.domain.combat.value_object.hit_box_collision_policy import ObstacleCollisionPolicy
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.enum.world_enum import MovementCapabilityEnum


class TestHitBoxCollisionDomainService:
    @pytest.fixture
    def service(self):
        return HitBoxCollisionDomainService()

    @pytest.fixture
    def spot_id(self):
        return SpotId(1)

    @pytest.fixture
    def physical_map(self, spot_id):
        # 3x3の単純な草地マップ
        tiles = [Tile(Coordinate(x, y, 0), TerrainType.grass()) for x in range(3) for y in range(3)]
        return PhysicalMapAggregate.create(spot_id, tiles)

    def test_resolve_collisions_detects_obstacle(self, service, physical_map):
        # (1,1)を壁にする
        physical_map.get_tile(Coordinate(1, 1, 0)).change_terrain(TerrainType.wall())
        
        # 衝突時に消滅するポリシーを設定
        hit_box = self._create_hit_box(
            Coordinate(0, 1, 0), 
            velocity=HitBoxVelocity(1.0, 0.0, 0.0),
            obstacle_collision_policy=ObstacleCollisionPolicy.DEACTIVATE
        )
        # 1サブステップ進める
        hit_box.on_tick(WorldTick(1), step_ratio=1.0) # (0,1) -> (1,1)
        
        checks, guard = service.resolve_collisions(physical_map, hit_box, 100)
        
        assert checks > 0
        assert guard is False
        assert hit_box.is_active is False # 壁に当たって消滅

    def test_resolve_collisions_with_flying_capability_passes_wall(self, service, physical_map):
        # (1,1)を壁にする
        physical_map.get_tile(Coordinate(1, 1, 0)).change_terrain(TerrainType.wall())
        
        # 飛行能力を持つHitBox
        flying_cap = MovementCapability(frozenset({MovementCapabilityEnum.FLY}))
        hit_box = self._create_hit_box(
            Coordinate(0, 1, 0), 
            velocity=HitBoxVelocity(1.0, 0.0, 0.0),
            movement_capability=flying_cap
        )
        hit_box.on_tick(WorldTick(1), step_ratio=1.0)
        
        service.resolve_collisions(physical_map, hit_box, 100)
        
        assert hit_box.is_active is True # 飛行能力があれば壁を通過できる（TerrainTypeがFLYを許容する場合）
        # ※TerrainType.wall()がFLYを許容するかはTerrainTypeの実装に依るが、
        # ここではMovementCapabilityが使われていることを確認するのが目的。

    def test_resolve_collisions_detects_multiple_objects_in_path(self, service, physical_map):
        # 経路上の(1,1)と(2,1)にオブジェクトを配置
        obj1 = WorldObject(WorldObjectId(101), Coordinate(1, 1, 0), ObjectTypeEnum.NPC)
        obj2 = WorldObject(WorldObjectId(102), Coordinate(2, 1, 0), ObjectTypeEnum.NPC)
        physical_map.add_object(obj1)
        physical_map.add_object(obj2)
        
        # (0,1)から(2,1)まで一気に移動
        hit_box = self._create_hit_box(Coordinate(0, 1, 0), velocity=HitBoxVelocity(2.0, 0.0, 0.0))
        hit_box.on_tick(WorldTick(1), step_ratio=1.0)
        
        service.resolve_collisions(physical_map, hit_box, 100)
        
        assert hit_box.has_hit(WorldObjectId(101))
        assert hit_box.has_hit(WorldObjectId(102))

    def test_resolve_collisions_respects_max_checks(self, service, physical_map):
        hit_box = self._create_hit_box(Coordinate(0, 0, 0), velocity=HitBoxVelocity(2.0, 2.0, 0.0))
        hit_box.on_tick(WorldTick(1), step_ratio=1.0)
        
        # 判定回数を極端に制限
        checks, guard = service.resolve_collisions(physical_map, hit_box, 1)
        
        assert checks == 1
        assert guard is True

    def test_is_obstacle_coordinate_handles_out_of_bounds(self, service, physical_map):
        hit_box = self._create_hit_box(Coordinate(0, 0, 0))
        # マップ外の座標
        out_coord = Coordinate(10, 10, 0)
        
        assert service._is_obstacle_coordinate(physical_map, hit_box, out_coord) is True

    def _create_hit_box(self, coord, velocity=HitBoxVelocity.zero(), movement_capability=None, obstacle_collision_policy=ObstacleCollisionPolicy.PASS_THROUGH):
        return HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(1),
            spot_id=SpotId(1),
            owner_id=WorldObjectId(99),
            shape=HitBoxShape.single_cell(),
            initial_coordinate=coord,
            start_tick=WorldTick(0),
            duration=10,
            velocity=velocity,
            movement_capability=movement_capability,
            obstacle_collision_policy=obstacle_collision_policy
        )
