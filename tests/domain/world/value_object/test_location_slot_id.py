"""LocationSlotId のテスト"""
import pytest

from ai_rpg_world.domain.world.value_object.location_slot_id import LocationSlotId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.exception.map_exception import (
    SpotIdValidationException,
    LocationAreaIdValidationException,
)


class TestLocationSlotId:
    """LocationSlotId のテスト"""

    class TestCreate:
        def test_create_from_vo_success(self):
            spot_id = SpotId.create(1)
            location_area_id = LocationAreaId.create(1)
            slot_id = LocationSlotId.create(spot_id, location_area_id)
            assert slot_id.spot_id == spot_id
            assert slot_id.location_area_id == location_area_id

        def test_create_from_int_success(self):
            slot_id = LocationSlotId.create(1, 1)
            assert slot_id.spot_id.value == 1
            assert slot_id.location_area_id.value == 1

        def test_create_invalid_spot_id_raises(self):
            with pytest.raises(SpotIdValidationException):
                LocationSlotId.create(0, 1)

        def test_create_invalid_location_area_id_raises(self):
            with pytest.raises(LocationAreaIdValidationException):
                LocationSlotId.create(1, 0)

    class TestEqualityAndHash:
        def test_eq_same_values(self):
            a = LocationSlotId.create(1, 2)
            b = LocationSlotId.create(1, 2)
            assert a == b

        def test_eq_different_spot_id(self):
            a = LocationSlotId.create(1, 2)
            b = LocationSlotId.create(2, 2)
            assert a != b

        def test_eq_different_location_area_id(self):
            a = LocationSlotId.create(1, 2)
            b = LocationSlotId.create(1, 3)
            assert a != b

        def test_hash_consistent_with_eq(self):
            a = LocationSlotId.create(1, 2)
            b = LocationSlotId.create(1, 2)
            assert hash(a) == hash(b)

        def test_hash_can_use_as_dict_key(self):
            d = {}
            d[LocationSlotId.create(1, 1)] = "a"
            d[LocationSlotId.create(1, 2)] = "b"
            assert d[LocationSlotId.create(1, 1)] == "a"
            assert d[LocationSlotId.create(1, 2)] == "b"
