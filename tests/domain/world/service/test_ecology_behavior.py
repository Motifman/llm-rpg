"""生態タイプ（ecology_type）に応じた行動のテスト"""

import pytest
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, BehaviorStateEnum, EcologyTypeEnum
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    AutonomousBehaviorComponent,
    ActorComponent,
)
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.service.behavior_service import BehaviorService
from ai_rpg_world.domain.world.service.hostility_service import ConfigurableHostilityService
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.infrastructure.world.pathfinding.astar_pathfinding_strategy import AStarPathfindingStrategy


class TestEcologyFleeOnly:
    """FLEE_ONLY: 発見したら逃走のみ"""

    @pytest.fixture
    def service(self):
        path = PathfindingService(AStarPathfindingStrategy())
        hostility = ConfigurableHostilityService(race_hostility_table={"goblin": {"human"}})
        return BehaviorService(path, hostility)

    @pytest.fixture
    def map_aggregate(self):
        tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(10) for y in range(10)]
        return PhysicalMapAggregate.create(SpotId(1), tiles)

    def test_flee_only_spots_target_goes_flee(self, service, map_aggregate):
        comp = AutonomousBehaviorComponent(
            race="goblin",
            vision_range=5,
            fov_angle=360,
            ecology_type=EcologyTypeEnum.FLEE_ONLY,
        )
        monster = WorldObject(
            WorldObjectId(100), Coordinate(5, 5), ObjectTypeEnum.NPC, is_blocking=False, component=comp
        )
        map_aggregate.add_object(monster)
        player = WorldObject(
            WorldObjectId(1), Coordinate(6, 5), ObjectTypeEnum.PLAYER, is_blocking=False, component=ActorComponent(race="human")
        )
        map_aggregate.add_object(player)
        service.plan_action(WorldObjectId(100), map_aggregate)
        assert comp.state == BehaviorStateEnum.FLEE
        assert comp.target_id == WorldObjectId(1)


class TestEcologyPatrolOnly:
    """PATROL_ONLY: 発見しても追わない"""

    @pytest.fixture
    def service(self):
        path = PathfindingService(AStarPathfindingStrategy())
        hostility = ConfigurableHostilityService(race_hostility_table={"goblin": {"human"}})
        return BehaviorService(path, hostility)

    @pytest.fixture
    def map_aggregate(self):
        tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(10) for y in range(10)]
        return PhysicalMapAggregate.create(SpotId(1), tiles)

    def test_patrol_only_ignores_target(self, service, map_aggregate):
        comp = AutonomousBehaviorComponent(
            race="goblin",
            vision_range=5,
            fov_angle=360,
            ecology_type=EcologyTypeEnum.PATROL_ONLY,
            state=BehaviorStateEnum.PATROL,
        )
        monster = WorldObject(
            WorldObjectId(100), Coordinate(5, 5), ObjectTypeEnum.NPC, is_blocking=False, component=comp
        )
        map_aggregate.add_object(monster)
        player = WorldObject(
            WorldObjectId(1), Coordinate(6, 5), ObjectTypeEnum.PLAYER, is_blocking=False, component=ActorComponent(race="human")
        )
        map_aggregate.add_object(player)
        service.plan_action(WorldObjectId(100), map_aggregate)
        assert comp.state == BehaviorStateEnum.PATROL
        assert comp.target_id is None


class TestEcologyAmbush:
    """AMBUSH: 初期位置から ambush_chase_range を超えると追わない"""

    @pytest.fixture
    def service(self):
        path = PathfindingService(AStarPathfindingStrategy())
        hostility = ConfigurableHostilityService(race_hostility_table={"goblin": {"human"}})
        return BehaviorService(path, hostility)

    @pytest.fixture
    def map_aggregate(self):
        tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(15) for y in range(10)]
        return PhysicalMapAggregate.create(SpotId(1), tiles)

    def test_ambush_in_range_chases(self, service, map_aggregate):
        comp = AutonomousBehaviorComponent(
            race="goblin",
            vision_range=10,
            fov_angle=360,
            ecology_type=EcologyTypeEnum.AMBUSH,
            ambush_chase_range=5,
        )
        comp.initial_position = Coordinate(5, 5)
        monster = WorldObject(
            WorldObjectId(100), Coordinate(5, 5), ObjectTypeEnum.NPC, is_blocking=False, component=comp
        )
        map_aggregate.add_object(monster)
        player = WorldObject(
            WorldObjectId(1), Coordinate(6, 5), ObjectTypeEnum.PLAYER, is_blocking=False, component=ActorComponent(race="human")
        )
        map_aggregate.add_object(player)
        service.plan_action(WorldObjectId(100), map_aggregate)
        assert comp.state == BehaviorStateEnum.CHASE
        assert comp.target_id == WorldObjectId(1)

    def test_ambush_out_of_range_does_not_chase(self, service, map_aggregate):
        comp = AutonomousBehaviorComponent(
            race="goblin",
            vision_range=10,
            fov_angle=360,
            ecology_type=EcologyTypeEnum.AMBUSH,
            ambush_chase_range=2,
        )
        comp.initial_position = Coordinate(5, 5)
        monster = WorldObject(
            WorldObjectId(100), Coordinate(5, 5), ObjectTypeEnum.NPC, is_blocking=False, component=comp
        )
        map_aggregate.add_object(monster)
        player = WorldObject(
            WorldObjectId(1), Coordinate(10, 5), ObjectTypeEnum.PLAYER, is_blocking=False, component=ActorComponent(race="human")
        )
        map_aggregate.add_object(player)
        service.plan_action(WorldObjectId(100), map_aggregate)
        assert comp.target_id is None
        assert comp.state == BehaviorStateEnum.IDLE
