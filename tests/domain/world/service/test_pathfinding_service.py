import pytest
from unittest.mock import MagicMock
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.domain.world.service.pathfinding_strategy import PathfindingStrategy, PathfindingMap
from ai_rpg_world.domain.world.exception.map_exception import PathNotFoundException, InvalidPathRequestException


class TestPathfindingService:
    @pytest.fixture
    def mock_strategy(self):
        return MagicMock(spec=PathfindingStrategy)

    @pytest.fixture
    def mock_map(self):
        return MagicMock(spec=PathfindingMap)

    @pytest.fixture
    def service(self, mock_strategy):
        return PathfindingService(mock_strategy)

    @pytest.fixture
    def capability(self):
        return MovementCapability.normal_walk()

    def test_calculate_path_success(self, service, mock_strategy, mock_map, capability):
        """正常系の経路算出"""
        start = Coordinate(0, 0)
        goal = Coordinate(2, 2)
        expected_path = [start, Coordinate(1, 1), goal]
        
        mock_map.is_passable.return_value = True
        mock_strategy.find_path.return_value = expected_path
        
        # 単純化を無効にしてテスト
        path = service.calculate_path(start, goal, mock_map, capability, smooth_path=False)
        
        assert path == expected_path
        mock_strategy.find_path.assert_called_once_with(start, goal, mock_map, capability, max_iterations=1000)

    def test_calculate_path_same_start_goal(self, service, mock_strategy, mock_map, capability):
        """開始点と目標地点が同じ場合"""
        start = Coordinate(0, 0)
        
        mock_map.is_passable.return_value = True
        
        path = service.calculate_path(start, start, mock_map, capability)
        
        assert path == [start]
        mock_strategy.find_path.assert_not_called()

    def test_calculate_path_invalid_start(self, service, mock_map, capability):
        """開始地点が通行不能な場合"""
        start = Coordinate(0, 0)
        goal = Coordinate(1, 1)
        
        mock_map.is_passable.side_effect = lambda c, cap: c != start
        
        with pytest.raises(InvalidPathRequestException) as exc:
            service.calculate_path(start, goal, mock_map, capability)
        assert "Start point" in str(exc.value)

    def test_calculate_path_invalid_goal(self, service, mock_map, capability):
        """目標地点が通行不能な場合"""
        start = Coordinate(0, 0)
        goal = Coordinate(1, 1)
        
        mock_map.is_passable.side_effect = lambda c, cap: c != goal
        
        with pytest.raises(InvalidPathRequestException) as exc:
            service.calculate_path(start, goal, mock_map, capability)
        assert "Goal point" in str(exc.value)

    def test_calculate_path_not_found_raises(self, service, mock_strategy, mock_map, capability):
        """経路が見つからない場合に例外を投げる"""
        start = Coordinate(0, 0)
        goal = Coordinate(2, 2)
        
        mock_map.is_passable.return_value = True
        mock_strategy.find_path.return_value = []
        
        with pytest.raises(PathNotFoundException):
            service.calculate_path(start, goal, mock_map, capability, ignore_errors=False)

    def test_calculate_path_not_found_ignore_errors(self, service, mock_strategy, mock_map, capability):
        """経路が見つからない場合に空リストを返す（ignore_errors=True）"""
        start = Coordinate(0, 0)
        goal = Coordinate(2, 2)
        
        mock_map.is_passable.return_value = True
        mock_strategy.find_path.return_value = []
        
        path = service.calculate_path(start, goal, mock_map, capability, ignore_errors=True)
        assert path == []

    def test_calculate_path_partial_not_allowed(self, service, mock_strategy, mock_map, capability):
        """部分経路を許可しない場合に例外を投げる"""
        start = Coordinate(0, 0)
        goal = Coordinate(2, 2)
        partial_path = [start, Coordinate(1, 1)] # ゴールに届かない
        
        mock_map.is_passable.return_value = True
        mock_strategy.find_path.return_value = partial_path
        
        with pytest.raises(PathNotFoundException) as exc:
            service.calculate_path(start, goal, mock_map, capability, allow_partial_path=False)
        assert "Complete path not found" in str(exc.value)

    def test_calculate_path_partial_allowed(self, service, mock_strategy, mock_map, capability):
        """部分経路を許可する場合に経路を返す"""
        start = Coordinate(0, 0)
        goal = Coordinate(2, 2)
        partial_path = [start, Coordinate(1, 1)]
        
        mock_map.is_passable.return_value = True
        mock_strategy.find_path.return_value = partial_path
        
        path = service.calculate_path(start, goal, mock_map, capability, allow_partial_path=True)
        assert path == partial_path

    def test_calculate_path_smoothing(self, service, mock_strategy, mock_map, capability):
        """経路の単純化が正しく行われるか"""
        start = Coordinate(0, 0)
        goal = Coordinate(2, 2)
        # 本来は 0,0 -> 1,1 -> 2,2 の経路
        raw_path = [start, Coordinate(1, 1), goal]
        
        mock_map.is_passable.return_value = True
        mock_strategy.find_path.return_value = raw_path
        # 0,0 から 2,2 が直接視認可能とする
        mock_map.is_visible.side_effect = lambda a, b: (a == start and b == goal) or (a == start and b == Coordinate(1, 1)) or (a == Coordinate(1, 1) and b == goal)
        
        # 単純化あり
        path_smoothed = service.calculate_path(start, goal, mock_map, capability, smooth_path=True)
        assert path_smoothed == [start, goal]
        
        # 単純化なし
        path_raw = service.calculate_path(start, goal, mock_map, capability, smooth_path=False)
        assert path_raw == raw_path
