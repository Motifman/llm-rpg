import pytest
from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.exception.map_exception import GatewayIdValidationException


class TestGatewayId:
    def test_create_with_int_success(self):
        gw_id = GatewayId(1)
        assert gw_id.value == 1
        assert str(gw_id) == "1"
        assert int(gw_id) == 1

    def test_create_with_string_success(self):
        gw_id = GatewayId.create("10")
        assert gw_id.value == 10

    def test_create_with_invalid_string_raises_error(self):
        with pytest.raises(GatewayIdValidationException):
            GatewayId.create("abc")

    def test_create_with_non_positive_int_raises_error(self):
        with pytest.raises(GatewayIdValidationException):
            GatewayId(0)
        with pytest.raises(GatewayIdValidationException):
            GatewayId(-1)

    def test_equality(self):
        assert GatewayId(1) == GatewayId(1)
        assert GatewayId(1) != GatewayId(2)
        assert hash(GatewayId(1)) == hash(GatewayId(1))
