import pytest
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.value_object.area import RectArea
from ai_rpg_world.domain.world.entity.location_area import LocationArea
from ai_rpg_world.domain.world.entity.gateway import Gateway
from ai_rpg_world.domain.world.event.map_events import (
    LocationEnteredEvent,
    LocationExitedEvent,
    GatewayTriggeredEvent
)
from ai_rpg_world.domain.world.exception.map_exception import (
    DuplicateLocationAreaException,
    LocationAreaNotFoundException,
    DuplicateGatewayException,
    GatewayNotFoundException
)


class TestPhysicalMapAggregateLocationGateway:
    @pytest.fixture
    def spot_id(self):
        return SpotId(1)

    @pytest.fixture
    def simple_tiles(self):
        tiles = []
        for x in range(5):
            for y in range(5):
                tiles.append(Tile(Coordinate(x, y), TerrainType.road()))
        return tiles

    @pytest.fixture
    def aggregate(self, spot_id, simple_tiles):
        return PhysicalMapAggregate.create(spot_id, simple_tiles)

    class TestLocationArea:
        def test_add_location_area_success(self, aggregate):
            # Given
            loc_id = LocationAreaId(1)
            area = RectArea(1, 2, 1, 2, 0, 0)
            loc = LocationArea(loc_id, area, "教室", "勉強する場所")

            # When
            aggregate.add_location_area(loc)

            # Then
            assert aggregate.get_location_area(loc_id) == loc
            assert loc in aggregate.get_all_location_areas()

        def test_add_duplicate_location_area_raises_error(self, aggregate):
            loc = LocationArea(LocationAreaId(1), RectArea(0, 0, 0, 0, 0, 0), "A", "B")
            aggregate.add_location_area(loc)
            with pytest.raises(DuplicateLocationAreaException):
                aggregate.add_location_area(loc)

        def test_remove_location_area_success(self, aggregate):
            loc_id = LocationAreaId(1)
            loc = LocationArea(loc_id, RectArea(0, 0, 0, 0, 0, 0), "A", "B")
            aggregate.add_location_area(loc)
            
            # When
            aggregate.remove_location_area(loc_id)
            
            # Then
            assert len(aggregate.get_all_location_areas()) == 0
            with pytest.raises(LocationAreaNotFoundException):
                aggregate.get_location_area(loc_id)

        def test_location_entered_event_on_move(self, aggregate):
            # Given
            loc_id = LocationAreaId(1)
            name = "秘密の部屋"
            desc = "誰も知らない部屋"
            loc = LocationArea(loc_id, RectArea(2, 2, 2, 2, 0, 0), name, desc)
            aggregate.add_location_area(loc)
            
            obj_id = WorldObjectId(1)
            aggregate.add_object(WorldObject(obj_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER))
            aggregate.clear_events()
            
            # When: Move into the location area
            aggregate.move_object(obj_id, Coordinate(2, 2, 0))
            
            # Then
            events = aggregate.get_events()
            assert any(isinstance(e, LocationEnteredEvent) for e in events)
            event = [e for e in events if isinstance(e, LocationEnteredEvent)][0]
            assert event.location_id == loc_id
            assert event.name == name
            assert event.description == desc
            assert event.object_id == obj_id

        def test_location_exited_event_on_move(self, aggregate):
            # Given
            loc_id = LocationAreaId(1)
            loc = LocationArea(loc_id, RectArea(0, 0, 0, 0, 0, 0), "A", "B")
            aggregate.add_location_area(loc)
            
            obj_id = WorldObjectId(1)
            aggregate.add_object(WorldObject(obj_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER))
            aggregate.clear_events()
            
            # When: Move out of the location area
            aggregate.move_object(obj_id, Coordinate(1, 1, 0))
            
            # Then
            events = aggregate.get_events()
            assert any(isinstance(e, LocationExitedEvent) for e in events)
            event = [e for e in events if isinstance(e, LocationExitedEvent)][0]
            assert event.location_id == loc_id
            assert event.object_id == obj_id

    class TestGateway:
        def test_add_gateway_success(self, aggregate):
            # Given
            gw_id = GatewayId(1)
            area = RectArea(4, 4, 4, 4, 0, 0)
            gw = Gateway(gw_id, "出口", area, SpotId(2), Coordinate(0, 0, 0))

            # When
            aggregate.add_gateway(gw)

            # Then
            assert aggregate.get_gateway(gw_id) == gw
            assert gw in aggregate.get_all_gateways()

        def test_add_duplicate_gateway_raises_error(self, aggregate):
            gw = Gateway(GatewayId(1), "G", RectArea(0, 0, 0, 0, 0, 0), SpotId(2), Coordinate(0, 0, 0))
            aggregate.add_gateway(gw)
            with pytest.raises(DuplicateGatewayException):
                aggregate.add_gateway(gw)

        def test_gateway_triggered_event_on_move(self, aggregate):
            # Given
            gw_id = GatewayId(1)
            target_spot = SpotId(2)
            landing_coord = Coordinate(5, 5, 0)
            gw = Gateway(gw_id, "ワープ門", RectArea(4, 4, 4, 4, 0, 0), target_spot, landing_coord)
            aggregate.add_gateway(gw)
            
            obj_id = WorldObjectId(1)
            aggregate.add_object(WorldObject(obj_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER))
            aggregate.clear_events()
            
            # When: Move into the gateway area
            aggregate.move_object(obj_id, Coordinate(4, 4, 0))
            
            # Then
            events = aggregate.get_events()
            assert any(isinstance(e, GatewayTriggeredEvent) for e in events)
            event = [e for e in events if isinstance(e, GatewayTriggeredEvent)][0]
            assert event.gateway_id == gw_id
            assert event.target_spot_id == target_spot
            assert event.landing_coordinate == landing_coord
            assert event.object_id == obj_id

    class TestEdgeCases:
        def test_inactive_location_area_does_not_trigger_event(self, aggregate):
            # Given
            loc_id = LocationAreaId(1)
            loc = LocationArea(loc_id, RectArea(2, 2, 2, 2, 0, 0), "A", "B", is_active=False)
            aggregate.add_location_area(loc)
            
            obj_id = WorldObjectId(1)
            aggregate.add_object(WorldObject(obj_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER))
            aggregate.clear_events()
            
            # When
            aggregate.move_object(obj_id, Coordinate(2, 2, 0))
            
            # Then
            assert not any(isinstance(e, LocationEnteredEvent) for e in aggregate.get_events())

        def test_inactive_gateway_does_not_trigger_event(self, aggregate):
            # Given
            gw_id = GatewayId(1)
            gw = Gateway(gw_id, "G", RectArea(2, 2, 2, 2, 0, 0), SpotId(2), Coordinate(0, 0, 0), is_active=False)
            aggregate.add_gateway(gw)
            
            obj_id = WorldObjectId(1)
            aggregate.add_object(WorldObject(obj_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER))
            aggregate.clear_events()
            
            # When
            aggregate.move_object(obj_id, Coordinate(2, 2, 0))
            
            # Then
            assert not any(isinstance(e, GatewayTriggeredEvent) for e in aggregate.get_events())

        def test_overlapping_location_areas_trigger_multiple_events(self, aggregate):
            # Given
            loc1 = LocationArea(LocationAreaId(1), RectArea(2, 2, 2, 2, 0, 0), "Area1", "Desc1")
            loc2 = LocationArea(LocationAreaId(2), RectArea(2, 2, 2, 2, 0, 0), "Area2", "Desc2")
            aggregate.add_location_area(loc1)
            aggregate.add_location_area(loc2)
            
            obj_id = WorldObjectId(1)
            aggregate.add_object(WorldObject(obj_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER))
            aggregate.clear_events()
            
            # When
            aggregate.move_object(obj_id, Coordinate(2, 2, 0))
            
            # Then
            events = [e for e in aggregate.get_events() if isinstance(e, LocationEnteredEvent)]
            assert len(events) == 2
            ids = {e.location_id for e in events}
            assert ids == {LocationAreaId(1), LocationAreaId(2)}
