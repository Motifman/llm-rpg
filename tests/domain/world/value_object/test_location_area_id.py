import pytest
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.exception.map_exception import LocationAreaIdValidationException


class TestLocationAreaId:
    def test_create_with_int_success(self):
        loc_id = LocationAreaId(1)
        assert loc_id.value == 1
        assert str(loc_id) == "1"
        assert int(loc_id) == 1

    def test_create_with_string_success(self):
        loc_id = LocationAreaId.create("10")
        assert loc_id.value == 10

    def test_create_with_invalid_string_raises_error(self):
        with pytest.raises(LocationAreaIdValidationException):
            LocationAreaId.create("abc")

    def test_create_with_non_positive_int_raises_error(self):
        with pytest.raises(LocationAreaIdValidationException):
            LocationAreaId(0)
        with pytest.raises(LocationAreaIdValidationException):
            LocationAreaId(-1)

    def test_equality(self):
        assert LocationAreaId(1) == LocationAreaId(1)
        assert LocationAreaId(1) != LocationAreaId(2)
        assert hash(LocationAreaId(1)) == hash(LocationAreaId(1))
