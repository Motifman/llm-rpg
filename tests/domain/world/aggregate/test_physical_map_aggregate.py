import pytest
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, TerrainTypeEnum, TriggerTypeEnum
from ai_rpg_world.domain.world.exception.map_exception import (
    TileNotFoundException,
    ObjectNotFoundException,
    DuplicateObjectException,
    InvalidPlacementException,
    InvalidMovementException
)
from ai_rpg_world.domain.world.event.map_events import (
    PhysicalMapCreatedEvent,
    WorldObjectMovedEvent,
    WorldObjectBlockingChangedEvent,
    WorldObjectAddedEvent,
    TileTerrainChangedEvent,
    TileTriggeredEvent
)
from ai_rpg_world.domain.world.entity.map_trigger import WarpTrigger, DamageTrigger


class TestPhysicalMapAggregate:
    @pytest.fixture
    def spot_id(self):
        return SpotId(1)

    @pytest.fixture
    def simple_tiles(self):
        tiles = []
        for x in range(3):
            for y in range(3):
                tiles.append(Tile(Coordinate(x, y), TerrainType.road()))
        return tiles

    @pytest.fixture
    def aggregate(self, spot_id, simple_tiles):
        return PhysicalMapAggregate.create(spot_id, simple_tiles)

    class TestCreate:
        def test_create_success(self, spot_id, simple_tiles):
            # When
            aggregate = PhysicalMapAggregate.create(spot_id, simple_tiles)
            
            # Then
            assert aggregate.spot_id == spot_id
            assert len(aggregate.get_all_tiles()) == 9
            events = aggregate.get_events()
            assert any(isinstance(e, PhysicalMapCreatedEvent) for e in events)

        def test_create_with_objects(self, spot_id, simple_tiles):
            # Given
            obj = WorldObject(WorldObjectId(1), Coordinate(1, 1), ObjectTypeEnum.CHEST)
            
            # When
            aggregate = PhysicalMapAggregate.create(spot_id, simple_tiles, [obj])
            
            # Then
            assert len(aggregate.get_all_objects()) == 1
            assert aggregate.is_walkable(Coordinate(1, 1)) is False

        def test_create_duplicate_object_id_raises_error(self, spot_id, simple_tiles):
            obj1 = WorldObject(WorldObjectId(1), Coordinate(0, 0), ObjectTypeEnum.CHEST)
            obj2 = WorldObject(WorldObjectId(1), Coordinate(1, 1), ObjectTypeEnum.CHEST)
            
            with pytest.raises(DuplicateObjectException):
                PhysicalMapAggregate.create(spot_id, simple_tiles, [obj1, obj2])

        def test_create_object_on_wall_raises_error(self, spot_id):
            tiles = [Tile(Coordinate(0, 0), TerrainType.wall())]
            obj = WorldObject(WorldObjectId(1), Coordinate(0, 0), ObjectTypeEnum.CHEST)
            
            with pytest.raises(InvalidPlacementException):
                PhysicalMapAggregate.create(spot_id, tiles, [obj])

        def test_create_object_out_of_bounds_raises_error(self, spot_id, simple_tiles):
            obj = WorldObject(WorldObjectId(1), Coordinate(9, 9), ObjectTypeEnum.CHEST)
            
            with pytest.raises(InvalidPlacementException):
                PhysicalMapAggregate.create(spot_id, simple_tiles, [obj])

    class TestMoveObject:
        def test_move_success(self, aggregate):
            # Given
            obj_id = WorldObjectId(1)
            start_coord = Coordinate(0, 0)
            end_coord = Coordinate(1, 1)
            obj = WorldObject(obj_id, start_coord, ObjectTypeEnum.SIGN, is_blocking=True)
            aggregate._add_object_to_internal_storage(obj)
            aggregate.clear_events()
            
            # When
            aggregate.move_object(obj_id, end_coord)
            
            # Then
            assert aggregate.get_object(obj_id).coordinate == end_coord
            assert aggregate.is_walkable(start_coord) is True
            assert aggregate.is_walkable(end_coord) is False
            
            events = aggregate.get_events()
            assert any(isinstance(e, WorldObjectMovedEvent) for e in events)

        def test_move_to_same_position_does_nothing(self, aggregate):
            obj_id = WorldObjectId(1)
            coord = Coordinate(0, 0)
            obj = WorldObject(obj_id, coord, ObjectTypeEnum.SIGN)
            aggregate._add_object_to_internal_storage(obj)
            aggregate.clear_events()
            
            aggregate.move_object(obj_id, coord)
            
            assert len(aggregate.get_events()) == 0

        def test_move_to_occupied_tile_raises_error(self, aggregate):
            obj1 = WorldObject(WorldObjectId(1), Coordinate(0, 0), ObjectTypeEnum.CHEST)
            obj2 = WorldObject(WorldObjectId(2), Coordinate(1, 1), ObjectTypeEnum.CHEST)
            aggregate._add_object_to_internal_storage(obj1)
            aggregate._add_object_to_internal_storage(obj2)
            
            with pytest.raises(InvalidMovementException):
                aggregate.move_object(WorldObjectId(1), Coordinate(1, 1))

        def test_move_to_wall_raises_error(self, spot_id):
            tiles = [
                Tile(Coordinate(0, 0), TerrainType.road()),
                Tile(Coordinate(1, 1), TerrainType.wall())
            ]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            obj_id = WorldObjectId(1)
            aggregate._add_object_to_internal_storage(WorldObject(obj_id, Coordinate(0, 0), ObjectTypeEnum.CHEST))
            
            with pytest.raises(InvalidMovementException):
                aggregate.move_object(obj_id, Coordinate(1, 1))

    class TestSetObjectBlocking:
        def test_set_blocking_updates_walkability(self, aggregate):
            # Given
            obj_id = WorldObjectId(1)
            coord = Coordinate(1, 1)
            obj = WorldObject(obj_id, coord, ObjectTypeEnum.DOOR, is_blocking=True)
            aggregate._add_object_to_internal_storage(obj)
            assert aggregate.is_walkable(coord) is False
            
            # When
            aggregate.set_object_blocking(obj_id, False)
            
            # Then
            assert aggregate.is_walkable(coord) is True
            events = aggregate.get_events()
            assert any(isinstance(e, WorldObjectBlockingChangedEvent) for e in events)

    class TestChangeTileTerrain:
        def test_change_terrain_success(self, aggregate, spot_id):
            # Given
            coord = Coordinate(0, 0)
            new_terrain = TerrainType.swamp()
            
            # When
            aggregate.change_tile_terrain(coord, new_terrain)
            
            # Then
            assert aggregate.get_tile(coord).terrain_type == new_terrain
            events = aggregate.get_events()
            assert any(isinstance(e, TileTerrainChangedEvent) for e in events)

        def test_change_to_wall_with_object_raises_error(self, aggregate):
            coord = Coordinate(1, 1)
            aggregate._add_object_to_internal_storage(WorldObject(WorldObjectId(1), coord, ObjectTypeEnum.CHEST))
            
            with pytest.raises(InvalidPlacementException):
                aggregate.change_tile_terrain(coord, TerrainType.wall())

    class TestGetTile:
        def test_get_tile_out_of_bounds_raises_error(self, aggregate):
            with pytest.raises(TileNotFoundException):
                aggregate.get_tile(Coordinate(99, 99))

    class TestAddObject:
        def test_add_object_success(self, aggregate):
            # Given
            obj = WorldObject(WorldObjectId(10), Coordinate(2, 2), ObjectTypeEnum.CHEST)
            
            # When
            aggregate.add_object(obj)
            
            # Then
            assert aggregate.get_object(WorldObjectId(10)) == obj
            assert aggregate.is_walkable(Coordinate(2, 2)) is False
            assert any(isinstance(e, WorldObjectAddedEvent) for e in aggregate.get_events())

    class TestSpatialQuery:
        def test_get_objects_in_range(self, spot_id):
            # Given
            tiles = [Tile(Coordinate(x, y), TerrainType.road()) for x in range(5) for y in range(5)]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            
            obj1 = WorldObject(WorldObjectId(1), Coordinate(1, 1), ObjectTypeEnum.CHEST)
            obj2 = WorldObject(WorldObjectId(2), Coordinate(2, 2), ObjectTypeEnum.CHEST)
            obj3 = WorldObject(WorldObjectId(3), Coordinate(4, 4), ObjectTypeEnum.CHEST)
            
            aggregate.add_object(obj1)
            aggregate.add_object(obj2)
            aggregate.add_object(obj3)
            
            # When
            in_range = aggregate.get_objects_in_range(Coordinate(2, 2), 2)
            
            # Then
            # Distance from (2,2): (1,1)=2, (2,2)=0, (4,4)=4
            assert len(in_range) == 2
            assert obj1 in in_range
            assert obj2 in in_range
            assert obj3 not in in_range

    class TestLineOfSight:
        def test_visible_no_obstacles(self, aggregate):
            assert aggregate.is_visible(Coordinate(0, 0), Coordinate(2, 2)) is True

        def test_not_visible_blocked_by_wall(self, spot_id):
            # Given
            tiles = [
                Tile(Coordinate(0, 0), TerrainType.road()),
                Tile(Coordinate(1, 1), TerrainType.wall()),
                Tile(Coordinate(2, 2), TerrainType.road())
            ]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            
            # When & Then
            assert aggregate.is_visible(Coordinate(0, 0), Coordinate(2, 2)) is False

        def test_not_visible_blocked_by_object(self, aggregate):
            # Given
            obj = WorldObject(WorldObjectId(1), Coordinate(1, 1), ObjectTypeEnum.SIGN, is_blocking=True)
            aggregate.add_object(obj)
            
            # When & Then
            assert aggregate.is_visible(Coordinate(0, 0), Coordinate(2, 2)) is False

        def test_visible_after_object_blocking_disabled(self, aggregate):
            # Given
            obj = WorldObject(WorldObjectId(1), Coordinate(1, 1), ObjectTypeEnum.DOOR, is_blocking=True)
            aggregate.add_object(obj)
            assert aggregate.is_visible(Coordinate(0, 0), Coordinate(2, 2)) is False
            
            # When
            aggregate.set_object_blocking(WorldObjectId(1), False)
            
            # Then
            assert aggregate.is_visible(Coordinate(0, 0), Coordinate(2, 2)) is True

    class TestTriggers:
        def test_warp_trigger_activation(self, aggregate):
            # Given
            target_spot = SpotId(2)
            target_coord = Coordinate(10, 10)
            warp = WarpTrigger(target_spot, target_coord)
            aggregate.get_tile(Coordinate(1, 1)).set_trigger(warp)
            
            # When
            trigger = aggregate.check_and_activate_trigger(Coordinate(1, 1), WorldObjectId(1))
            
            # Then
            assert isinstance(trigger, WarpTrigger)
            assert trigger.target_spot_id == target_spot
            
            events = aggregate.get_events()
            assert any(isinstance(e, TileTriggeredEvent) and e.trigger_type == TriggerTypeEnum.WARP for e in events)

        def test_no_trigger_activation(self, aggregate):
            # When
            trigger = aggregate.check_and_activate_trigger(Coordinate(0, 0))
            
            # Then
            assert trigger is None
            assert not any(isinstance(e, TileTriggeredEvent) for e in aggregate.get_events())
