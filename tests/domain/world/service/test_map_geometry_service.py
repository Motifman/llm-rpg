import pytest
from unittest.mock import MagicMock
from ai_rpg_world.domain.world.service.map_geometry_service import MapGeometryService, VisibilityMap
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate

class TestMapGeometryService:
    def test_is_visible_no_obstacles(self):
        """障害物がない場合に視認可能であること"""
        map_data = MagicMock(spec=VisibilityMap)
        map_data.is_sight_blocked.return_value = False
        
        # 直線
        assert MapGeometryService.is_visible(Coordinate(0, 0, 0), Coordinate(5, 0, 0), map_data) is True
        # 斜め
        assert MapGeometryService.is_visible(Coordinate(0, 0, 0), Coordinate(5, 5, 0), map_data) is True
        # 3D
        assert MapGeometryService.is_visible(Coordinate(0, 0, 0), Coordinate(5, 5, 5), map_data) is True

    def test_is_visible_blocked(self):
        """障害物がある場合に視認不可であること"""
        map_data = MagicMock(spec=VisibilityMap)
        
        def is_blocked(coord):
            # (2, 0, 0) に障害物
            return coord == Coordinate(2, 0, 0)
            
        map_data.is_sight_blocked.side_effect = is_blocked
        
        assert MapGeometryService.is_visible(Coordinate(0, 0, 0), Coordinate(5, 0, 0), map_data) is False
        # 障害物を避けるルートなら視認可能
        assert MapGeometryService.is_visible(Coordinate(0, 0, 0), Coordinate(0, 5, 0), map_data) is True

    def test_is_visible_same_coordinate(self):
        """同じ座標同士は常に視認可能であること"""
        map_data = MagicMock(spec=VisibilityMap)
        coord = Coordinate(1, 1, 1)
        assert MapGeometryService.is_visible(coord, coord, map_data) is True
