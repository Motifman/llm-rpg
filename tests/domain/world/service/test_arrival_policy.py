"""ArrivalPolicy の単体テスト。正常ケース・例外ケース・境界ケースを網羅する。"""

import pytest
from ai_rpg_world.domain.world.service.arrival_policy import ArrivalPolicy, ArrivalCheckResult
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.location_area import LocationArea
from ai_rpg_world.domain.world.value_object.area import PointArea, RectArea
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType


def _create_minimal_player_status(
    player_id: int = 1,
    current_spot_id: SpotId = None,
    current_coordinate: Coordinate = None,
    goal_destination_type: str = None,
    goal_spot_id: SpotId = None,
    goal_location_area_id: LocationAreaId = None,
    goal_world_object_id: WorldObjectId = None,
) -> PlayerStatusAggregate:
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=PlayerId(player_id),
        base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(1000),
        hp=Hp.create(100, 100),
        mp=Mp.create(50, 50),
        stamina=Stamina.create(100, 100),
        current_spot_id=current_spot_id,
        current_coordinate=current_coordinate,
        goal_destination_type=goal_destination_type,
        goal_spot_id=goal_spot_id,
        goal_location_area_id=goal_location_area_id,
        goal_world_object_id=goal_world_object_id,
    )


def _create_physical_map_with_location_area(
    spot_id: int = 1,
    location_area_id: int = 10,
    location_contains: Coordinate = None,
) -> PhysicalMapAggregate:
    tiles = []
    for x in range(5):
        for y in range(5):
            tiles.append(Tile(Coordinate(x, y, 0), TerrainType.road()))
    area = PointArea(location_contains or Coordinate(2, 2, 0))
    loc_area = LocationArea(
        LocationAreaId(location_area_id),
        area,
        "TestRoom",
        "Test room description",
    )
    return PhysicalMapAggregate.create(
        SpotId(spot_id),
        tiles,
        location_areas=[loc_area],
    )


def _create_physical_map_with_object(
    spot_id: int = 1,
    object_id: int = 100,
    object_coord: Coordinate = None,
) -> PhysicalMapAggregate:
    tiles = []
    for x in range(5):
        for y in range(5):
            tiles.append(Tile(Coordinate(x, y, 0), TerrainType.road()))
    obj_coord = object_coord or Coordinate(2, 2, 0)
    obj = WorldObject(
        WorldObjectId(object_id),
        obj_coord,
        ObjectTypeEnum.CHEST,
    )
    return PhysicalMapAggregate.create(
        SpotId(spot_id),
        tiles,
        objects=[obj],
    )


class TestCheck:
    """check のテスト"""

    class TestNotArrived:
        def test_returns_not_arrived_when_goal_spot_id_is_none(self):
            status = _create_minimal_player_status(
                current_spot_id=SpotId(1),
                current_coordinate=Coordinate(1, 1, 0),
                goal_destination_type="spot",
                goal_spot_id=None,
            )
            result = ArrivalPolicy.check(status, None)
            assert result == ArrivalCheckResult.NOT_ARRIVED

        def test_returns_not_arrived_when_current_spot_differs_from_goal(self):
            status = _create_minimal_player_status(
                current_spot_id=SpotId(1),
                current_coordinate=Coordinate(1, 1, 0),
                goal_destination_type="spot",
                goal_spot_id=SpotId(2),
            )
            result = ArrivalPolicy.check(status, None)
            assert result == ArrivalCheckResult.NOT_ARRIVED

        def test_returns_not_arrived_when_location_type_player_outside_area(self):
            phys_map = _create_physical_map_with_location_area(
                location_contains=Coordinate(2, 2, 0),
            )
            status = _create_minimal_player_status(
                current_spot_id=SpotId(1),
                current_coordinate=Coordinate(0, 0, 0),
                goal_destination_type="location",
                goal_spot_id=SpotId(1),
                goal_location_area_id=LocationAreaId(10),
            )
            result = ArrivalPolicy.check(status, phys_map)
            assert result == ArrivalCheckResult.NOT_ARRIVED

        def test_returns_not_arrived_when_object_type_player_not_adjacent(self):
            phys_map = _create_physical_map_with_object(object_coord=Coordinate(2, 2, 0))
            status = _create_minimal_player_status(
                current_spot_id=SpotId(1),
                current_coordinate=Coordinate(0, 0, 0),
                goal_destination_type="object",
                goal_spot_id=SpotId(1),
                goal_world_object_id=WorldObjectId(100),
            )
            result = ArrivalPolicy.check(status, phys_map)
            assert result == ArrivalCheckResult.NOT_ARRIVED

        def test_returns_not_arrived_when_location_type_physical_map_is_none(self):
            status = _create_minimal_player_status(
                current_spot_id=SpotId(1),
                current_coordinate=Coordinate(2, 2, 0),
                goal_destination_type="location",
                goal_spot_id=SpotId(1),
                goal_location_area_id=LocationAreaId(10),
            )
            result = ArrivalPolicy.check(status, None)
            assert result == ArrivalCheckResult.NOT_ARRIVED

        def test_returns_not_arrived_when_object_type_physical_map_is_none(self):
            status = _create_minimal_player_status(
                current_spot_id=SpotId(1),
                current_coordinate=Coordinate(2, 2, 0),
                goal_destination_type="object",
                goal_spot_id=SpotId(1),
                goal_world_object_id=WorldObjectId(100),
            )
            result = ArrivalPolicy.check(status, None)
            assert result == ArrivalCheckResult.NOT_ARRIVED

        def test_returns_not_arrived_when_goal_location_area_id_is_none_for_location_type(self):
            phys_map = _create_physical_map_with_location_area()
            status = _create_minimal_player_status(
                current_spot_id=SpotId(1),
                current_coordinate=Coordinate(2, 2, 0),
                goal_destination_type="location",
                goal_spot_id=SpotId(1),
                goal_location_area_id=None,
            )
            result = ArrivalPolicy.check(status, phys_map)
            assert result == ArrivalCheckResult.NOT_ARRIVED

        def test_returns_not_arrived_when_current_coordinate_is_none_for_location_type(self):
            phys_map = _create_physical_map_with_location_area()
            status = _create_minimal_player_status(
                current_spot_id=SpotId(1),
                current_coordinate=None,
                goal_destination_type="location",
                goal_spot_id=SpotId(1),
                goal_location_area_id=LocationAreaId(10),
            )
            result = ArrivalPolicy.check(status, phys_map)
            assert result == ArrivalCheckResult.NOT_ARRIVED

    class TestArrived:
        def test_returns_arrived_when_spot_type_and_same_spot(self):
            status = _create_minimal_player_status(
                current_spot_id=SpotId(1),
                current_coordinate=Coordinate(1, 1, 0),
                goal_destination_type="spot",
                goal_spot_id=SpotId(1),
            )
            result = ArrivalPolicy.check(status, None)
            assert result == ArrivalCheckResult.ARRIVED

        def test_returns_arrived_when_location_type_and_player_inside_area(self):
            phys_map = _create_physical_map_with_location_area(
                location_contains=Coordinate(2, 2, 0),
            )
            status = _create_minimal_player_status(
                current_spot_id=SpotId(1),
                current_coordinate=Coordinate(2, 2, 0),
                goal_destination_type="location",
                goal_spot_id=SpotId(1),
                goal_location_area_id=LocationAreaId(10),
            )
            result = ArrivalPolicy.check(status, phys_map)
            assert result == ArrivalCheckResult.ARRIVED

        def test_returns_arrived_when_location_type_and_rect_area_contains_player(self):
            tiles = []
            for x in range(5):
                for y in range(5):
                    tiles.append(Tile(Coordinate(x, y, 0), TerrainType.road()))
            rect_area = RectArea(1, 3, 1, 3, 0, 0)
            loc_area = LocationArea(
                LocationAreaId(10),
                rect_area,
                "TestRoom",
                "Test room",
            )
            phys_map = PhysicalMapAggregate.create(
                SpotId(1),
                tiles,
                location_areas=[loc_area],
            )
            status = _create_minimal_player_status(
                current_spot_id=SpotId(1),
                current_coordinate=Coordinate(2, 2, 0),
                goal_destination_type="location",
                goal_spot_id=SpotId(1),
                goal_location_area_id=LocationAreaId(10),
            )
            result = ArrivalPolicy.check(status, phys_map)
            assert result == ArrivalCheckResult.ARRIVED

        def test_returns_arrived_when_object_type_and_player_adjacent(self):
            phys_map = _create_physical_map_with_object(
                object_id=100,
                object_coord=Coordinate(2, 2, 0),
            )
            status = _create_minimal_player_status(
                current_spot_id=SpotId(1),
                current_coordinate=Coordinate(1, 2, 0),
                goal_destination_type="object",
                goal_spot_id=SpotId(1),
                goal_world_object_id=WorldObjectId(100),
            )
            result = ArrivalPolicy.check(status, phys_map)
            assert result == ArrivalCheckResult.ARRIVED

        def test_returns_arrived_when_object_type_and_player_same_cell(self):
            phys_map = _create_physical_map_with_object(
                object_id=100,
                object_coord=Coordinate(2, 2, 0),
            )
            status = _create_minimal_player_status(
                current_spot_id=SpotId(1),
                current_coordinate=Coordinate(2, 2, 0),
                goal_destination_type="object",
                goal_spot_id=SpotId(1),
                goal_world_object_id=WorldObjectId(100),
            )
            result = ArrivalPolicy.check(status, phys_map)
            assert result == ArrivalCheckResult.ARRIVED

        def test_returns_not_arrived_when_object_type_and_player_diagonally_adjacent(self):
            # 元の仕様: distance_to は Manhattan 距離。斜め隣接 (1,1)-(2,2) は距離 2 のため到着扱いにならない
            phys_map = _create_physical_map_with_object(
                object_id=100,
                object_coord=Coordinate(2, 2, 0),
            )
            status = _create_minimal_player_status(
                current_spot_id=SpotId(1),
                current_coordinate=Coordinate(1, 1, 0),
                goal_destination_type="object",
                goal_spot_id=SpotId(1),
                goal_world_object_id=WorldObjectId(100),
            )
            result = ArrivalPolicy.check(status, phys_map)
            assert result == ArrivalCheckResult.NOT_ARRIVED

    class TestGoalDisappeared:
        def test_returns_goal_disappeared_when_location_area_not_found(self):
            phys_map = _create_physical_map_with_location_area(location_area_id=10)
            status = _create_minimal_player_status(
                current_spot_id=SpotId(1),
                current_coordinate=Coordinate(2, 2, 0),
                goal_destination_type="location",
                goal_spot_id=SpotId(1),
                goal_location_area_id=LocationAreaId(999),
            )
            result = ArrivalPolicy.check(status, phys_map)
            assert result == ArrivalCheckResult.GOAL_DISAPPEARED

        def test_returns_goal_disappeared_when_object_not_found(self):
            phys_map = _create_physical_map_with_object(object_id=100)
            status = _create_minimal_player_status(
                current_spot_id=SpotId(1),
                current_coordinate=Coordinate(2, 2, 0),
                goal_destination_type="object",
                goal_spot_id=SpotId(1),
                goal_world_object_id=WorldObjectId(999),
            )
            result = ArrivalPolicy.check(status, phys_map)
            assert result == ArrivalCheckResult.GOAL_DISAPPEARED

    class TestEdgeCases:
        def test_returns_not_arrived_when_goal_destination_type_is_none(self):
            status = _create_minimal_player_status(
                current_spot_id=SpotId(1),
                current_coordinate=Coordinate(1, 1, 0),
                goal_destination_type=None,
                goal_spot_id=SpotId(1),
            )
            result = ArrivalPolicy.check(status, None)
            assert result == ArrivalCheckResult.NOT_ARRIVED

        def test_returns_not_arrived_when_goal_destination_type_is_unknown_string(self):
            status = _create_minimal_player_status(
                current_spot_id=SpotId(1),
                current_coordinate=Coordinate(1, 1, 0),
                goal_destination_type="unknown",
                goal_spot_id=SpotId(1),
            )
            result = ArrivalPolicy.check(status, None)
            assert result == ArrivalCheckResult.NOT_ARRIVED
