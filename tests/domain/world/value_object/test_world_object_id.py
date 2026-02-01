import pytest
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.exception.map_exception import WorldObjectIdValidationException


class TestWorldObjectId:
    def test_create_success(self):
        id1 = WorldObjectId(1)
        assert id1.value == 1
        assert str(id1) == "1"
        assert int(id1) == 1

    def test_create_from_int(self):
        id1 = WorldObjectId.create(10)
        assert id1.value == 10

    def test_create_from_str(self):
        id1 = WorldObjectId.create("20")
        assert id1.value == 20

    def test_create_invalid_str_raises_error(self):
        with pytest.raises(WorldObjectIdValidationException):
            WorldObjectId.create("abc")

    def test_negative_id_raises_error(self):
        with pytest.raises(WorldObjectIdValidationException):
            WorldObjectId(-1)

    def test_zero_id_raises_error(self):
        with pytest.raises(WorldObjectIdValidationException):
            WorldObjectId(0)

    def test_equality(self):
        assert WorldObjectId(1) == WorldObjectId(1)
        assert WorldObjectId(1) != WorldObjectId(2)
