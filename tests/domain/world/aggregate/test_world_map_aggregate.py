import pytest
from ai_rpg_world.domain.world.aggregate.world_map_aggregate import WorldMapAggregate
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.connection import Connection
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world.exception.map_exception import (
    SpotNotFoundException,
    InvalidConnectionException
)
from ai_rpg_world.domain.world.event.map_events import (
    WorldMapCreatedEvent,
    SpotAddedEvent,
    ConnectionAddedEvent
)


class TestWorldMapAggregate:
    @pytest.fixture
    def world_id(self):
        return WorldId(1)

    @pytest.fixture
    def spot1(self):
        return Spot(SpotId(1), "Town", "A starting town", SpotCategoryEnum.TOWN)

    @pytest.fixture
    def spot2(self):
        return Spot(SpotId(2), "Forest", "A dark forest", SpotCategoryEnum.FIELD)

    @pytest.fixture
    def aggregate(self, world_id):
        return WorldMapAggregate.create(world_id)

    class TestCreate:
        def test_create_success(self, world_id):
            # When
            aggregate = WorldMapAggregate.create(world_id)
            
            # Then
            assert aggregate.world_id == world_id
            events = aggregate.get_events()
            assert any(isinstance(e, WorldMapCreatedEvent) for e in events)

    class TestAddSpot:
        def test_add_spot_success(self, aggregate, spot1):
            # When
            aggregate.add_spot(spot1)
            
            # Then
            assert aggregate.get_spot(spot1.spot_id) == spot1
            events = aggregate.get_events()
            assert any(isinstance(e, SpotAddedEvent) for e in events)

        def test_get_non_existent_spot_raises_error(self, aggregate):
            with pytest.raises(SpotNotFoundException):
                aggregate.get_spot(SpotId(999))

    class TestAddConnection:
        def test_add_connection_success(self, aggregate, spot1, spot2):
            # Given
            aggregate.add_spot(spot1)
            aggregate.add_spot(spot2)
            connection = Connection(spot1.spot_id, spot2.spot_id)
            
            # When
            aggregate.add_connection(connection)
            
            # Then
            assert connection in aggregate.get_all_connections()
            assert spot2.spot_id in aggregate.get_connected_spots(spot1.spot_id)
            events = aggregate.get_events()
            assert any(isinstance(e, ConnectionAddedEvent) for e in events)

        def test_add_duplicate_connection_allowed(self, aggregate, spot1, spot2):
            aggregate.add_spot(spot1)
            aggregate.add_spot(spot2)
            connection = Connection(spot1.spot_id, spot2.spot_id)
            
            aggregate.add_connection(connection)
            aggregate.add_connection(connection)
            
            assert len(aggregate.get_all_connections()) == 2

        def test_add_self_connection_raises_error(self, aggregate, spot1):
            aggregate.add_spot(spot1)
            # Connection self check is in Connection VO but let's check aggregate check too
            with pytest.raises(InvalidConnectionException):
                aggregate.add_connection(Connection(spot1.spot_id, spot1.spot_id))

        def test_add_connection_with_missing_source_raises_error(self, aggregate, spot1, spot2):
            aggregate.add_spot(spot2)
            with pytest.raises(SpotNotFoundException):
                aggregate.add_connection(Connection(spot1.spot_id, spot2.spot_id))

        def test_add_connection_with_missing_dest_raises_error(self, aggregate, spot1, spot2):
            aggregate.add_spot(spot1)
            with pytest.raises(SpotNotFoundException):
                aggregate.add_connection(Connection(spot1.spot_id, spot2.spot_id))
