import pytest
from ai_rpg_world.domain.world.entity.gateway import Gateway
from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.area import RectArea
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate

class TestGateway:
    def test_creation(self):
        gw_id = GatewayId(1)
        area = RectArea(0, 0, 0, 0, 0, 0)
        target_spot = SpotId(2)
        landing = Coordinate(5, 5, 0)
        gw = Gateway(gw_id, "ゲート", area, target_spot, landing)
        
        assert gw.gateway_id == gw_id
        assert gw.name == "ゲート"
        assert gw.area == area
        assert gw.target_spot_id == target_spot
        assert gw.landing_coordinate == landing
        assert gw.is_active is True

    def test_is_active_behavior(self):
        area = RectArea(0, 0, 0, 0, 0, 0)
        gw = Gateway(GatewayId(1), "G", area, SpotId(2), Coordinate(0, 0, 0))
        
        assert gw.contains(Coordinate(0, 0, 0)) is True
        gw.set_active(False)
        assert gw.contains(Coordinate(0, 0, 0)) is False
