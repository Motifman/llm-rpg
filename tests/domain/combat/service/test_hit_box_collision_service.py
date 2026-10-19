from unittest.mock import Mock

import pytest

from ai_rpg_world.domain.combat.aggregate.hit_box_aggregate import HitBoxAggregate
from ai_rpg_world.domain.combat.event.combat_events import HitBoxDeactivatedEvent, HitBoxObstacleCollidedEvent
from ai_rpg_world.domain.combat.service.hit_box_collision_service import HitBoxCollisionDomainService
from ai_rpg_world.domain.combat.value_object.hit_box_collision_policy import ObstacleCollisionPolicy
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.combat.value_object.hit_box_velocity import HitBoxVelocity
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.enum.world_enum import MovementCapabilityEnum, ObjectTypeEnum
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


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

    @pytest.mark.parametrize(
        ("capabilities", "policy", "obstacle_coordinates"),
        [
            pytest.param(
                frozenset({MovementCapabilityEnum.FLY}),
                ObstacleCollisionPolicy.PASS_THROUGH,
                [Coordinate(0, 1, 0)],
                id="fly-only-pass-through",
            ),
            pytest.param(
                frozenset({MovementCapabilityEnum.WALK, MovementCapabilityEnum.FLY}),
                ObstacleCollisionPolicy.DEACTIVATE,
                [],
                id="walk-and-fly-deactivate",
            ),
        ],
    )
    def test_resolve_collisions_respects_movement_capabilities(
        self, service, physical_map, capabilities, policy, obstacle_coordinates
    ):
        """飛行で壁を通過し、歩行能力もあれば停止設定でも出発草地と壁の両方を通れる。"""
        physical_map.get_tile(Coordinate(1, 1, 0)).change_terrain(TerrainType.wall())
        hit_box = self._create_hit_box(
            Coordinate(0, 1, 0),
            velocity=HitBoxVelocity(1.0, 0.0, 0.0),
            movement_capability=MovementCapability(capabilities),
            obstacle_collision_policy=policy,
        )
        hit_box.on_tick(WorldTick(1), step_ratio=1.0)
        hit_box.clear_events()

        checks, guard = service.resolve_collisions(physical_map, hit_box, 100)

        assert hit_box.is_active is True
        assert checks == 2
        assert guard is False
        events = hit_box.get_events()
        assert [
            (event.collision_coordinate, event.obstacle_collision_policy)
            for event in events
            if isinstance(event, HitBoxObstacleCollidedEvent)
        ] == [(coordinate, policy.value) for coordinate in obstacle_coordinates]
        assert not any(isinstance(event, HitBoxDeactivatedEvent) for event in events)

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

    @pytest.mark.parametrize(
        ("policy", "remains_active", "deactivation_reasons"),
        [
            pytest.param(ObstacleCollisionPolicy.PASS_THROUGH, True, [], id="pass-through"),
            pytest.param(
                ObstacleCollisionPolicy.DEACTIVATE, False, ["obstacle_collision"], id="deactivate"
            ),
        ],
    )
    def test_resolve_collisions_treats_missing_tile_as_obstacle(
        self, service, physical_map, policy, remains_active, deactivation_reasons
    ):
        """タイルのない正座標への衝突を通知し、通過設定では生存、停止設定では失効する。"""
        hit_box = self._create_hit_box(Coordinate(0, 0, 0), obstacle_collision_policy=policy)
        out_coord = Coordinate(10, 10, 0)
        hit_box.teleport_to(out_coord)
        # 静止更新で経路起点も揃え、途中の別のマップ外セルでは失効しないようにする。
        hit_box.on_tick(WorldTick(1))
        assert hit_box.is_active is True
        assert hit_box.is_expired(WorldTick(1)) is False
        assert hit_box.get_all_covered_coordinates() == [out_coord]
        hit_box.clear_events()

        checks, guard = service.resolve_collisions(physical_map, hit_box, 100)

        assert checks == 1
        assert guard is False
        assert hit_box.is_active is remains_active
        events = hit_box.get_events()
        assert [
            (event.collision_coordinate, event.obstacle_collision_policy)
            for event in events
            if isinstance(event, HitBoxObstacleCollidedEvent)
        ] == [(out_coord, policy.value)]
        assert [
            event.reason for event in events if isinstance(event, HitBoxDeactivatedEvent)
        ] == deactivation_reasons

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
