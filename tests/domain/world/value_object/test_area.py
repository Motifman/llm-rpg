import pytest
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.area import PointArea, RectArea, CircleArea


class TestArea:
    """Area値オブジェクトのテスト"""

    class TestPointArea:
        def test_contains(self):
            target = Coordinate(1, 2, 3)
            area = PointArea(target)
            
            assert area.contains(Coordinate(1, 2, 3)) is True
            assert area.contains(Coordinate(1, 2, 0)) is False
            assert area.contains(Coordinate(0, 0, 0)) is False

    class TestRectArea:
        def test_boundary_values(self):
            # 1,1,0 から 2,2,0 の範囲 (0は避けることで境界外テストをしやすくする)
            area = RectArea(1, 2, 1, 2, 0, 0)
            
            # 境界上（角）
            assert area.contains(Coordinate(1, 1, 0)) is True
            assert area.contains(Coordinate(2, 2, 0)) is True
            assert area.contains(Coordinate(1, 2, 0)) is True
            assert area.contains(Coordinate(2, 1, 0)) is True
            
            # 境界のわずかに外側 (x, y は0以上を維持)
            assert area.contains(Coordinate(0, 1, 0)) is False
            assert area.contains(Coordinate(1, 0, 0)) is False
            assert area.contains(Coordinate(3, 1, 0)) is False
            assert area.contains(Coordinate(1, 3, 0)) is False
            assert area.contains(Coordinate(1, 1, 1)) is False
            assert area.contains(Coordinate(1, 1, -1)) is False

        def test_contains(self):
            area = RectArea(0, 5, 0, 5, 0, 1)
            
            # 内側
            assert area.contains(Coordinate(0, 0, 0)) is True
            assert area.contains(Coordinate(5, 5, 1)) is True
            assert area.contains(Coordinate(2, 3, 0)) is True
            
            # 外側
            assert area.contains(Coordinate(6, 0, 0)) is False
            assert area.contains(Coordinate(0, 6, 0)) is False
            assert area.contains(Coordinate(0, 0, 2)) is False
            assert area.contains(Coordinate(0, 0, -1)) is False

        def test_from_coordinates(self):
            c1 = Coordinate(5, 5, 1)
            c2 = Coordinate(0, 0, 0)
            area = RectArea.from_coordinates(c1, c2)
            
            assert area.min_x == 0
            assert area.max_x == 5
            assert area.min_y == 0
            assert area.max_y == 5
            assert area.min_z == 0
            assert area.max_z == 1
            assert area.contains(Coordinate(2, 2, 0)) is True

    class TestCircleArea:
        def test_boundary_values_manhattan(self):
            # 中心(2,2,0), 半径2 (マンハッタン距離)
            area = CircleArea(Coordinate(2, 2, 0), 2)
            
            # 距離2の点（境界上）
            assert area.contains(Coordinate(2, 2, 0)) is True # 距離0
            assert area.contains(Coordinate(4, 2, 0)) is True # 距離2
            assert area.contains(Coordinate(0, 2, 0)) is True # 距離2
            assert area.contains(Coordinate(2, 4, 0)) is True # 距離2
            assert area.contains(Coordinate(2, 0, 0)) is True # 距離2
            assert area.contains(Coordinate(3, 3, 0)) is True # 距離2
            assert area.contains(Coordinate(2, 2, 2)) is True # 距離2
            assert area.contains(Coordinate(2, 2, -2)) is True # 距離2
            
            # 距離3の点（境界の外側）
            assert area.contains(Coordinate(5, 2, 0)) is False # 距離3
            assert area.contains(Coordinate(4, 3, 0)) is False # 距離3
            assert area.contains(Coordinate(3, 3, 1)) is False # 距離3

        def test_contains_manhattan(self):
            center = Coordinate(2, 2, 0)
            area = CircleArea(center, 2)
            
            # 距離2以内
            assert area.contains(Coordinate(2, 2, 0)) is True # 距離0
            assert area.contains(Coordinate(4, 2, 0)) is True # 距離2
            assert area.contains(Coordinate(2, 0, 0)) is True # 距離2
            assert area.contains(Coordinate(2, 2, 2)) is True # 距離2
            assert area.contains(Coordinate(3, 3, 0)) is True # 距離2
            
            # 距離2を超える
            assert area.contains(Coordinate(4, 3, 0)) is False # 距離3
            assert area.contains(Coordinate(2, 2, 3)) is False # 距離3
            assert area.contains(Coordinate(0, 0, 0)) is False # 距離4
