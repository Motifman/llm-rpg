import pytest
from ai_rpg_world.domain.world.value_object.area_trigger_id import AreaTriggerId
from ai_rpg_world.domain.world.exception.map_exception import AreaTriggerIdValidationException


class TestAreaTriggerId:
    def test_create_success(self):
        id1 = AreaTriggerId(1)
        assert id1.value == 1
        assert str(id1) == "1"
        assert int(id1) == 1

    def test_create_from_int(self):
        id1 = AreaTriggerId.create(10)
        assert id1.value == 10

    def test_create_from_str(self):
        id1 = AreaTriggerId.create("20")
        assert id1.value == 20

    def test_create_invalid_str_raises_error(self):
        with pytest.raises(AreaTriggerIdValidationException):
            AreaTriggerId.create("abc")

    def test_negative_id_raises_error(self):
        with pytest.raises(AreaTriggerIdValidationException):
            AreaTriggerId(-1)

    def test_zero_id_raises_error(self):
        with pytest.raises(AreaTriggerIdValidationException):
            AreaTriggerId(0)

    def test_equality(self):
        assert AreaTriggerId(1) == AreaTriggerId(1)
        assert AreaTriggerId(1) != AreaTriggerId(2)
