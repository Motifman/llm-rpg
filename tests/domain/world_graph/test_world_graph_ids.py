import pytest

from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    ConnectionIdValidationException,
    EntityIdValidationException,
    SpotGraphIdValidationException,
    SpotObjectIdValidationException,
    SubLocationIdValidationException,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.sub_location_id import SubLocationId


class TestEntityId:
    def test_create_valid(self):
        e = EntityId.create(1)
        assert e.value == 1

    def test_create_from_str(self):
        assert EntityId.create("42").value == 42

    def test_non_positive_raises(self):
        with pytest.raises(EntityIdValidationException):
            EntityId.create(0)
        with pytest.raises(EntityIdValidationException):
            EntityId.create(-1)

    def test_invalid_str_raises(self):
        with pytest.raises(EntityIdValidationException):
            EntityId.create("x")


class TestConnectionId:
    def test_create_valid(self):
        assert ConnectionId.create(1).value == 1

    def test_non_positive_raises(self):
        with pytest.raises(ConnectionIdValidationException):
            ConnectionId.create(0)


class TestSpotGraphId:
    def test_create_valid(self):
        assert SpotGraphId.create(1).value == 1

    def test_non_positive_raises(self):
        with pytest.raises(SpotGraphIdValidationException):
            SpotGraphId.create(0)


class TestSubLocationId:
    def test_create(self):
        assert SubLocationId.create(1).value == 1

    def test_invalid(self):
        with pytest.raises(SubLocationIdValidationException):
            SubLocationId.create(0)


class TestSpotObjectId:
    def test_create(self):
        assert SpotObjectId.create(1).value == 1

    def test_invalid(self):
        with pytest.raises(SpotObjectIdValidationException):
            SpotObjectId.create(-1)
