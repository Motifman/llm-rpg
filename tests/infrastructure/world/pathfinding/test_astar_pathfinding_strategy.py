import pytest
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.infrastructure.world.pathfinding.astar_pathfinding_strategy import AStarPathfindingStrategy


class TestAStarPathfindingStrategy:
    @pytest.fixture
    def strategy(self):
        return AStarPathfindingStrategy()

    @pytest.fixture
    def capability(self):
        return MovementCapability.normal_walk()

    @pytest.fixture
    def simple_map(self):
        # 5x5の単純なマップを作成
        tiles = []
        for x in range(5):
            for y in range(5):
                # (2, 1), (2, 2), (2, 3) に壁を置く
                if x == 2 and 1 <= y <= 3:
                    terrain = TerrainType.wall()
                else:
                    terrain = TerrainType.road()
                tiles.append(Tile(Coordinate(x, y), terrain))
        
        return PhysicalMapAggregate.create(SpotId(1), tiles)

    def test_find_path_diagonal(self, strategy, capability, simple_map):
        """斜め移動を含む経路探索（マンハッタン距離より短くなるはず）"""
        # (0, 0) から (1, 1) へ。斜めなら1ステップ（コスト1.41）、直線なら2ステップ（コスト2.0）
        start = Coordinate(0, 0)
        goal = Coordinate(1, 1)
        
        path = strategy.find_path(start, goal, simple_map, capability)
        
        assert path == [start, goal]

    def test_find_path_with_limit_returns_partial(self, strategy, capability, simple_map):
        """探索制限に達した場合に部分経路を返す"""
        start = Coordinate(0, 0)
        goal = Coordinate(4, 4)
        
        # 極端に少ない試行回数を設定
        max_iterations = 2
        path = strategy.find_path(start, goal, simple_map, capability, max_iterations=max_iterations)
        
        assert len(path) > 0
        assert path[0] == start
        assert path[-1] != goal # ゴールには到達していないはず
        # 少なくとも開始地点よりはゴールに近づいているノードが最後にあるはず
        assert strategy._heuristic(path[-1], goal) <= strategy._heuristic(start, goal)

    def test_find_path_ghost_walk(self, strategy):
        """GHOST_WALK能力を持つ場合、壁を通り抜ける"""
        # 4x4のマップを作成し、(2,2)を壁で囲む
        tiles = []
        for x in range(4):
            for y in range(4):
                if x == 2 and y == 2:
                    # 目的地
                    tiles.append(Tile(Coordinate(x, y), TerrainType.road()))
                elif 1 <= x <= 3 and 1 <= y <= 3:
                    # 目的地を囲む壁
                    tiles.append(Tile(Coordinate(x, y), TerrainType.wall()))
                else:
                    # 外側
                    tiles.append(Tile(Coordinate(x, y), TerrainType.road()))
        
        map_data = PhysicalMapAggregate.create(SpotId(5), tiles)
        
        # 通常の能力では到達不能（完全に囲まれているため）
        normal_cap = MovementCapability.normal_walk()
        path_normal = strategy.find_path(Coordinate(0, 0), Coordinate(2, 2), map_data, normal_cap)
        assert path_normal == []
        
        # ゴースト能力なら到達可能
        ghost_cap = MovementCapability.ghost()
        path_ghost = strategy.find_path(Coordinate(0, 0), Coordinate(2, 2), map_data, ghost_cap)
        assert len(path_ghost) > 0
        assert path_ghost[-1] == Coordinate(2, 2)

    def test_find_path_extreme_costs(self, strategy, capability):
        """コストの極端な差を考慮した経路探索"""
        # 直進：道路(1.0) -> 沼地(100.0) -> 道路(1.0) = 102.0
        # 迂回：道路(1.0) x 10マス = 10.0
        tiles = []
        # 直進ルート (0,0) -> (1,0) -> ... -> (10,0)
        tiles.append(Tile(Coordinate(0, 0), TerrainType.road()))
        tiles.append(Tile(Coordinate(1, 0), TerrainType.swamp())) # 非常に高いコスト
        for x in range(2, 11):
            tiles.append(Tile(Coordinate(x, 0), TerrainType.road()))
            
        # 迂回ルート (0,0) -> (0,1) -> (1,1) -> ... -> (10,1) -> (10,0)
        for x in range(11):
            tiles.append(Tile(Coordinate(x, 1), TerrainType.road()))
            
        map_data = PhysicalMapAggregate.create(SpotId(6), tiles)
        
        path = strategy.find_path(Coordinate(0, 0), Coordinate(10, 0), map_data, capability)
        
        # 迂回ルート（y=1を通る）が選ばれるはず
        assert any(p.y == 1 for p in path)
        assert Coordinate(1, 0) not in path # 沼地は避ける

    def test_find_path_with_obstacle(self, strategy, capability, simple_map):
        """障害物を回避する経路探索"""
        # (1, 2) から (3, 2) へ。 (2, 2) は壁。
        start = Coordinate(1, 2)
        goal = Coordinate(3, 2)
        
        path = strategy.find_path(start, goal, simple_map, capability)
        
        assert len(path) > 0
        assert path[0] == start
        assert path[-1] == goal
        # 壁(2, 2)を避けているか確認
        assert Coordinate(2, 2) not in path
        # 最短経路は (1,2) -> (1,1) -> (2,1) -> (3,1) -> (3,2) の5マス、または y=0 や y=4 を通るルート
        # (1,2) -> (1,0) -> (2,0) -> (3,0) -> (3,2) など。
        # 今回のコスト設定では ROAD(1.0) なので、マンハッタン距離+αの長さになるはず
        assert len(path) >= 5 

    def test_path_not_found(self, strategy, capability):
        """経路が見つからない場合（孤立した地点）"""
        # 四方を壁で囲まれた地点
        tiles = [
            Tile(Coordinate(0, 0), TerrainType.road()),
            Tile(Coordinate(1, 0), TerrainType.wall()),
            Tile(Coordinate(0, 1), TerrainType.wall()),
            Tile(Coordinate(1, 1), TerrainType.wall()),
            Tile(Coordinate(2, 2), TerrainType.road()), # 目的地
        ]
        map_data = PhysicalMapAggregate.create(SpotId(2), tiles)
        
        path = strategy.find_path(Coordinate(0, 0), Coordinate(2, 2), map_data, capability)
        
        assert path == []

    def test_find_path_different_costs(self, strategy, capability):
        """コストが異なる場合の経路探索（遠回りでも低コストを選ぶか）"""
        # 直進ルートに非常に高いコストを設定
        # 0,0 (start)
        # 1,0 (swamp, cost 100.0)
        # 0,1 (road, cost 1.0)
        # 1,1 (road, cost 1.0)
        # 2,1 (road, cost 1.0)
        # 2,0 (goal)
        
        tiles = [
            Tile(Coordinate(0, 0), TerrainType.road()),
            Tile(Coordinate(1, 0), TerrainType.swamp()), # 高コスト
            Tile(Coordinate(2, 0), TerrainType.road()),
            Tile(Coordinate(0, 1), TerrainType.road()),
            Tile(Coordinate(1, 1), TerrainType.road()),
            Tile(Coordinate(2, 1), TerrainType.road()),
        ]
        map_data = PhysicalMapAggregate.create(SpotId(3), tiles)
        
        path = strategy.find_path(Coordinate(0, 0), Coordinate(2, 0), map_data, capability)
        
        # 斜め移動 (0,0) -> (1,1) -> (2,0) のコストは 1.41 + 1.41 = 2.82
        # 直進 (0,0) -> (1,0) -> (2,0) のコストは 100.0 + 1.0 = 101.0
        # よって斜め移動が選ばれるはず。
        assert Coordinate(1, 1) in path
        assert Coordinate(1, 0) not in path

    def test_find_path_with_z_axis(self, strategy, capability):
        """Z軸（高低差）を含む経路探索"""
        # (0,0,0) -> (0,0,1) -> (1,0,1)
        tiles = [
            Tile(Coordinate(0, 0, 0), TerrainType.road()),
            Tile(Coordinate(0, 0, 1), TerrainType.road()),
            Tile(Coordinate(1, 0, 1), TerrainType.road()),
        ]
        map_data = PhysicalMapAggregate.create(SpotId(4), tiles)
        
        path = strategy.find_path(Coordinate(0, 0, 0), Coordinate(1, 0, 1), map_data, capability)
        
        assert path == [Coordinate(0, 0, 0), Coordinate(0, 0, 1), Coordinate(1, 0, 1)]

    def test_find_path_large_map(self, strategy, capability):
        """大規模マップ（50x50）での経路探索"""
        size = 50
        tiles = []
        for x in range(size):
            for y in range(size):
                tiles.append(Tile(Coordinate(x, y), TerrainType.road()))
        
        map_data = PhysicalMapAggregate.create(SpotId(10), tiles)
        
        start = Coordinate(0, 0)
        goal = Coordinate(size - 1, size - 1)
        
        # 探索制限を十分大きく設定
        path = strategy.find_path(start, goal, map_data, capability, max_iterations=5000)
        
        assert len(path) > 0
        assert path[0] == start
        assert path[-1] == goal
        # 最短経路（斜め移動を含む）の長さは size と一致するはず（0,0 から 49,49 は 49ステップ）
        assert len(path) == size
