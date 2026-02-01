import pytest
from ai_rpg_world.domain.world.entity.location_area import LocationArea
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.area import RectArea
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate

class TestLocationArea:
    def test_creation(self):
        loc_id = LocationAreaId(1)
        area = RectArea(0, 10, 0, 10, 0, 0)
        loc = LocationArea(loc_id, area, "テストエリア", "説明")
        
        assert loc.location_id == loc_id
        assert loc.area == area
        assert loc.name == "テストエリア"
        assert loc.description == "説明"
        assert loc.is_active is True

    def test_contains(self):
        area = RectArea(0, 5, 0, 5, 0, 0)
        loc = LocationArea(LocationAreaId(1), area, "A", "B")
        
        assert loc.contains(Coordinate(2, 2, 0)) is True
        assert loc.contains(Coordinate(6, 6, 0)) is False

    def test_is_active_behavior(self):
        area = RectArea(0, 5, 0, 5, 0, 0)
        loc = LocationArea(LocationAreaId(1), area, "A", "B")
        
        loc.set_active(False)
        assert loc.is_active is False
        assert loc.contains(Coordinate(2, 2, 0)) is False
        
        loc.set_active(True)
        assert loc.contains(Coordinate(2, 2, 0)) is True

    def test_update_info(self):
        loc = LocationArea(LocationAreaId(1), RectArea(0, 0, 0, 0, 0, 0), "旧名", "旧説明")
        loc.update_info(name="新名", description="新説明")
        assert loc.name == "新名"
        assert loc.description == "新説明"
        
        loc.update_info(name="さらに新名")
        assert loc.name == "さらに新名"
        assert loc.description == "新説明"
