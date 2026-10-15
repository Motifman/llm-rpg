import pytest

from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum
from ai_rpg_world.domain.world.exception.map_exception import (
    DuplicateObjectException,
    InvalidMovementException,
    ObjectNotFoundException,
)
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId


class TestPhysicalMapAggregateMultiObjects:
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

    def test_multiple_non_blocking_objects_can_share_coordinate(self, aggregate):
        # Given: Two players (non-blocking)
        p1_id = WorldObjectId(1)
        p2_id = WorldObjectId(2)
        coord = Coordinate(2, 2, 0)
        
        # When: Adding both to the same coordinate
        aggregate.add_object(WorldObject(p1_id, coord, ObjectTypeEnum.PLAYER, is_blocking=False))
        aggregate.add_object(WorldObject(p2_id, coord, ObjectTypeEnum.PLAYER, is_blocking=False))
        
        # Then: Both should exist at the same coordinate
        assert sorted(obj.object_id.value for obj in aggregate.get_objects_at(coord)) == [1, 2]
        assert aggregate.get_object(p1_id).coordinate == coord
        assert aggregate.get_object(p2_id).coordinate == coord

    def test_blocking_object_cannot_be_placed_where_objects_exist(self, aggregate):
        # Given: A player at (2,2)
        p1_id = WorldObjectId(1)
        coord = Coordinate(2, 2, 0)
        aggregate.add_object(WorldObject(p1_id, coord, ObjectTypeEnum.PLAYER, is_blocking=False))
        
        # When: Trying to add a chest (blocking) at the same coordinate
        chest_id = WorldObjectId(2)
        with pytest.raises(DuplicateObjectException, match="Cannot place blocking object"):
            aggregate.add_object(WorldObject(chest_id, coord, ObjectTypeEnum.CHEST, is_blocking=True))

    def test_non_blocking_object_cannot_enter_coordinate_with_blocking_object(self, aggregate):
        # Given: A chest (blocking) at (2,2)
        chest_id = WorldObjectId(1)
        coord = Coordinate(2, 2, 0)
        aggregate.add_object(WorldObject(chest_id, coord, ObjectTypeEnum.CHEST, is_blocking=True))
        
        # When: A player tries to move to (2,2)
        p1_id = WorldObjectId(2)
        aggregate.add_object(WorldObject(p1_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER, is_blocking=False))
        
        with pytest.raises(InvalidMovementException, match="blocked by another object"):
            aggregate.move_object(p1_id, coord, WorldTick(10))

    def test_cannot_set_object_to_blocking_if_sharing_coordinate(self, aggregate):
        # Given: Two players at (2,2)
        p1_id = WorldObjectId(1)
        p2_id = WorldObjectId(2)
        coord = Coordinate(2, 2, 0)
        aggregate.add_object(WorldObject(p1_id, coord, ObjectTypeEnum.PLAYER, is_blocking=False))
        aggregate.add_object(WorldObject(p2_id, coord, ObjectTypeEnum.PLAYER, is_blocking=False))
        
        # When: Trying to set p1 to blocking
        with pytest.raises(DuplicateObjectException, match="Cannot set object .* to blocking"):
            aggregate.set_object_blocking(p1_id, True)

    def test_remove_object_updates_positions_correctly(self, aggregate):
        # Given: Two players at (2,2)
        p1_id = WorldObjectId(1)
        p2_id = WorldObjectId(2)
        coord = Coordinate(2, 2, 0)
        aggregate.add_object(WorldObject(p1_id, coord, ObjectTypeEnum.PLAYER, is_blocking=False))
        aggregate.add_object(WorldObject(p2_id, coord, ObjectTypeEnum.PLAYER, is_blocking=False))
        
        # When: Removing p1
        aggregate.remove_object(p1_id)
        
        # Then: p2 should still be there, but p1 should be gone
        assert [obj.object_id for obj in aggregate.get_objects_at(coord)] == [p2_id]
        assert aggregate.get_object(p2_id).coordinate == coord
        with pytest.raises(ObjectNotFoundException):
            aggregate.get_object(p1_id)
