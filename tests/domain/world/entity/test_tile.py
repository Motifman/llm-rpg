from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType

def test_tile_creation():
    coord = Coordinate(1, 2)
    terrain = TerrainType.road()
    tile = Tile(coord, terrain)
    
    assert tile.coordinate == coord
    assert tile.terrain_type == terrain
    assert tile.is_walkable is True
    assert tile.movement_cost.value == 1.0

def test_tile_walkable_override():
    tile = Tile(Coordinate(0, 0), TerrainType.road())
    assert tile.is_walkable is True
    
    tile.override_walkable(False)
    assert tile.is_walkable is False
    
    tile.reset_walkable()
    assert tile.is_walkable is True

def test_tile_impassable_terrain():
    tile = Tile(Coordinate(0, 0), TerrainType.wall())
    assert tile.is_walkable is False
    
    tile.override_walkable(True)
    assert tile.is_walkable is True
