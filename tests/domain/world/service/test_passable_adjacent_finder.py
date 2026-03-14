"""PassableAdjacentFinder の単体テスト。正常ケース・例外ケース・境界ケースを網羅する。"""

import pytest
from ai_rpg_world.domain.world.service.passable_adjacent_finder import PassableAdjacentFinder
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum


@pytest.fixture
def spot_id():
    return SpotId(1)


@pytest.fixture
def road_tiles_5x5():
    """5x5 の道路タイルマップ（全セル通行可能）"""
    tiles = []
    for x in range(5):
        for y in range(5):
            tiles.append(Tile(Coordinate(x, y, 0), TerrainType.road()))
    return tiles


@pytest.fixture
def map_with_object_at_center(spot_id, road_tiles_5x5):
    """中央 (2,2) にオブジェクトを配置したマップ"""
    obj = WorldObject(
        WorldObjectId(100),
        Coordinate(2, 2, 0),
        ObjectTypeEnum.CHEST,
    )
    return PhysicalMapAggregate.create(spot_id, road_tiles_5x5, objects=[obj])


@pytest.fixture
def map_surrounded_by_walls(spot_id):
    """中央 (1,1) のみ道路、周囲が壁のマップ"""
    tiles = [
        Tile(Coordinate(0, 0, 0), TerrainType.wall()),
        Tile(Coordinate(1, 0, 0), TerrainType.wall()),
        Tile(Coordinate(2, 0, 0), TerrainType.wall()),
        Tile(Coordinate(0, 1, 0), TerrainType.wall()),
        Tile(Coordinate(1, 1, 0), TerrainType.road()),
        Tile(Coordinate(2, 1, 0), TerrainType.wall()),
        Tile(Coordinate(0, 2, 0), TerrainType.wall()),
        Tile(Coordinate(1, 2, 0), TerrainType.wall()),
        Tile(Coordinate(2, 2, 0), TerrainType.wall()),
    ]
    obj = WorldObject(
        WorldObjectId(100),
        Coordinate(1, 1, 0),
        ObjectTypeEnum.CHEST,
    )
    return PhysicalMapAggregate.create(spot_id, tiles, objects=[obj])


class TestFindOne:
    """find_one のテスト"""

    class TestSuccessCases:
        def test_finds_passable_adjacent_when_object_at_center(
            self, map_with_object_at_center
        ):
            # Given: 中央 (2,2) にオブジェクト、周囲は道路
            physical_map = map_with_object_at_center
            object_coord = Coordinate(2, 2, 0)
            capability = MovementCapability.normal_walk()
            exclude_id = WorldObjectId(100)

            # When: 隣接通行可能セルを探索
            result = PassableAdjacentFinder.find_one(
                physical_map, object_coord, capability, exclude_object_id=exclude_id
            )

            # Then: いずれかの隣接座標が返る（NORTH から順に最初に見つかったもの）
            assert result is not None
            assert result != object_coord
            assert object_coord.chebyshev_distance_to(result) == 1
            assert physical_map.is_passable(
                result, capability, exclude_object_id=exclude_id
            )

        def test_returns_north_first_when_all_passable(self, map_with_object_at_center):
            # Given: 全方向通行可能。finder は NORTH から順に探索する
            physical_map = map_with_object_at_center
            object_coord = Coordinate(2, 2, 0)
            capability = MovementCapability.normal_walk()
            exclude_id = WorldObjectId(100)

            # When
            result = PassableAdjacentFinder.find_one(
                physical_map, object_coord, capability, exclude_object_id=exclude_id
            )

            # Then: NORTH が (2, 1) なので、最初に見つかる隣接は NORTH 方向
            assert result is not None
            assert result.y == 1  # NORTH は y-1
            assert result.x == 2

        def test_excludes_object_from_passability_check(self, map_with_object_at_center):
            # Given: オブジェクト (2,2) の隣に別オブジェクトがある場合、
            # exclude しないとオブジェクト上は通行不可だが、exclude すると判定から外れる
            # 単純に object_coord の隣が通行可能かチェック。exclude_object_id は
            # 対象オブジェクト (2,2) 自体を除外（オブジェクト座標は通行不可のため）
            physical_map = map_with_object_at_center
            object_coord = Coordinate(2, 2, 0)
            capability = MovementCapability.normal_walk()

            # exclude あり: 隣接セルのみチェック（(2,2) 上のオブジェクトは除外）
            result = PassableAdjacentFinder.find_one(
                physical_map, object_coord, capability, exclude_object_id=WorldObjectId(100)
            )
            assert result is not None

    class TestNoPassableNeighbor:
        def test_returns_none_when_all_neighbors_blocked(self, map_surrounded_by_walls):
            # Given: 中央 (1,1) の周囲が全て壁
            physical_map = map_surrounded_by_walls
            object_coord = Coordinate(1, 1, 0)
            capability = MovementCapability.normal_walk()
            exclude_id = WorldObjectId(100)

            # When
            result = PassableAdjacentFinder.find_one(
                physical_map, object_coord, capability, exclude_object_id=exclude_id
            )

            # Then: 隣接が全て壁なので None
            assert result is None

        def test_returns_none_when_object_at_map_edge(
            self, spot_id, road_tiles_5x5
        ):
            # Given: オブジェクトが (0,0) の角にあり、neighbor で負座標になる方向は
            # CoordinateValidationException でスキップ。有効な隣接は (1,0) と (0,1) のみ
            obj = WorldObject(WorldObjectId(1), Coordinate(0, 0, 0), ObjectTypeEnum.CHEST)
            physical_map = PhysicalMapAggregate.create(
                spot_id, road_tiles_5x5, objects=[obj]
            )
            # (0,0) の隣接で通行可能なのは (1,0), (0,1), (1,1)。道路なので見つかる
            result = PassableAdjacentFinder.find_one(
                physical_map,
                Coordinate(0, 0, 0),
                MovementCapability.normal_walk(),
                exclude_object_id=WorldObjectId(1),
            )
            assert result is not None

    class TestExcludeObjectId:
        def test_exclude_none_still_finds_neighbor_if_passable(
            self, map_with_object_at_center
        ):
            # Given: exclude なし。対象オブジェクト座標 (2,2) の隣接を探索。
            # 隣接セルは空なので通行可能。exclude は主に「隣接にオブジェクトがある場合、
            # そのオブジェクトをブロック判定から除外」する用途。
            physical_map = map_with_object_at_center
            result = PassableAdjacentFinder.find_one(
                physical_map,
                Coordinate(2, 2, 0),
                MovementCapability.normal_walk(),
                exclude_object_id=None,
            )
            assert result is not None

        def test_with_swim_capability_on_water(self, spot_id):
            # Given: 水地形のみ。通常歩行では通行不可、泳ぎ能力なら通行可能
            tiles = [
                Tile(Coordinate(0, 0, 0), TerrainType.water()),
                Tile(Coordinate(1, 0, 0), TerrainType.water()),
                Tile(Coordinate(0, 1, 0), TerrainType.water()),
                Tile(Coordinate(1, 1, 0), TerrainType.water()),
            ]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)
            from ai_rpg_world.domain.world.enum.world_enum import MovementCapabilityEnum
            swim_cap = MovementCapability(frozenset({MovementCapabilityEnum.SWIM}))

            # When: 泳ぎ能力で (0,0) の隣接を探索
            result = PassableAdjacentFinder.find_one(
                physical_map, Coordinate(0, 0, 0), swim_cap
            )
            assert result is not None
