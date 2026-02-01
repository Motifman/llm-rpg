import pytest
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.exception.map_exception import SpotNameEmptyException


def test_spot_creation_with_parent():
    # Given
    spot_id = SpotId(1)
    parent_id = SpotId(10)
    name = "教室"
    description = "学校の教室"
    
    # When
    spot = Spot(spot_id, name, description, SpotCategoryEnum.OTHER, parent_id)
    
    # Then
    assert spot.spot_id == spot_id
    assert spot.name == name
    assert spot.description == description
    assert spot.parent_id == parent_id


def test_spot_creation_without_parent():
    # Given
    spot_id = SpotId(1)
    name = "街"
    description = "賑やかな街"
    
    # When
    spot = Spot(spot_id, name, description)
    
    # Then
    assert spot.parent_id is None


def test_spot_creation_empty_name_raises_error():
    with pytest.raises(SpotNameEmptyException):
        Spot(SpotId(1), "", "description")
