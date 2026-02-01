from typing import List, Dict, Optional, Any
from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.map_trigger import MapTrigger
from ai_rpg_world.domain.world.event.map_events import (
    PhysicalMapCreatedEvent,
    WorldObjectStateChangedEvent,
    WorldObjectBlockingChangedEvent,
    WorldObjectMovedEvent,
    WorldObjectAddedEvent,
    TileTerrainChangedEvent,
    TileTriggeredEvent
)
from ai_rpg_world.domain.world.exception.map_exception import (
    TileNotFoundException, 
    ObjectNotFoundException,
    DuplicateObjectException,
    InvalidPlacementException,
    InvalidMovementException
)


class PhysicalMapAggregate(AggregateRoot):
    """物理マップ（タイルマップ）の集約"""
    
    def __init__(
        self,
        spot_id: SpotId,
        tiles: Dict[Coordinate, Tile],
        objects: List[WorldObject] = None
    ):
        super().__init__()
        self._spot_id = spot_id
        self._tiles = tiles
        self._objects: Dict[WorldObjectId, WorldObject] = {}
        self._object_positions: Dict[Coordinate, WorldObjectId] = {}
        
        if objects:
            for obj in objects:
                self._add_object_to_internal_storage(obj)

    @classmethod
    def create(cls, spot_id: SpotId, tiles: List[Tile], objects: List[WorldObject] = None) -> "PhysicalMapAggregate":
        tile_dict = {tile.coordinate: tile for tile in tiles}
        aggregate = cls(spot_id, tile_dict, objects)
        aggregate.add_event(PhysicalMapCreatedEvent.create(
            aggregate_id=spot_id,
            aggregate_type="PhysicalMapAggregate",
            spot_id=spot_id
        ))
        return aggregate

    def _add_object_to_internal_storage(self, obj: WorldObject):
        """内部ストレージにオブジェクトを追加し、バリデーションを行う"""
        if obj.object_id in self._objects:
            raise DuplicateObjectException(f"Object ID {obj.object_id} already exists")
        
        # 座標のバリデーション
        self._validate_placement(obj.coordinate)
        
        # 内部データの更新
        self._objects[obj.object_id] = obj
        self._object_positions[obj.coordinate] = obj.object_id
        
        # オブジェクトによる通行制限を反映
        if obj.is_blocking:
            self._update_tile_walkability(obj.coordinate, False)

    def _validate_placement(self, coordinate: Coordinate):
        """指定された座標にオブジェクトを配置可能かチェックする"""
        # 1. タイルが存在するか
        if coordinate not in self._tiles:
            raise InvalidPlacementException(f"Coordinate {coordinate} is out of map bounds")
        
        # 2. 壁の上ではないか
        tile = self._tiles[coordinate]
        if not tile.terrain_type.is_walkable:
            raise InvalidPlacementException(f"Cannot place object on non-walkable terrain at {coordinate}")
        
        # 3. 既にオブジェクトが存在しないか
        if coordinate in self._object_positions:
            raise DuplicateObjectException(f"Another object already exists at {coordinate}")

    @property
    def spot_id(self) -> SpotId:
        return self._spot_id

    def get_tile(self, coordinate: Coordinate) -> Tile:
        if coordinate not in self._tiles:
            raise TileNotFoundException(f"Tile not found at {coordinate} in spot {self._spot_id}")
        return self._tiles[coordinate]

    def is_walkable(self, coordinate: Coordinate) -> bool:
        try:
            tile = self.get_tile(coordinate)
            return tile.is_walkable
        except TileNotFoundException:
            return False

    def get_object(self, object_id: WorldObjectId) -> WorldObject:
        if object_id not in self._objects:
            raise ObjectNotFoundException(f"Object {object_id} not found in spot {self._spot_id}")
        return self._objects[object_id]

    def set_object_blocking(self, object_id: WorldObjectId, is_blocking: bool):
        obj = self.get_object(object_id)
        if obj.is_blocking == is_blocking:
            return
            
        obj.set_blocking(is_blocking)
        # 物理マップの通行可能性を更新
        self._update_tile_walkability(obj.coordinate, not is_blocking)
        
        self.add_event(WorldObjectBlockingChangedEvent.create(
            aggregate_id=object_id,
            aggregate_type="WorldObject",
            object_id=object_id,
            is_blocking=is_blocking
        ))

    def move_object(self, object_id: WorldObjectId, new_coordinate: Coordinate):
        obj = self.get_object(object_id)
        old_coordinate = obj.coordinate
        
        if old_coordinate == new_coordinate:
            return

        # 移動先のバリデーション
        try:
            self._validate_placement(new_coordinate)
        except (InvalidPlacementException, DuplicateObjectException) as e:
            raise InvalidMovementException(f"Cannot move object to {new_coordinate}: {str(e)}")
            
        # 移動処理
        if obj.is_blocking:
            self._update_tile_walkability(old_coordinate, True)
            self._update_tile_walkability(new_coordinate, False)
            
        # 位置管理の更新
        del self._object_positions[old_coordinate]
        self._object_positions[new_coordinate] = object_id
        obj.move_to(new_coordinate)
        
        self.add_event(WorldObjectMovedEvent.create(
            aggregate_id=object_id,
            aggregate_type="WorldObject",
            object_id=object_id,
            from_coordinate=old_coordinate,
            to_coordinate=new_coordinate
        ))

    def change_tile_terrain(self, coordinate: Coordinate, new_terrain_type: TerrainType):
        """タイルの地形を変更する"""
        tile = self.get_tile(coordinate)
        # 地形が変わることでオブジェクトが不正な位置になる場合はエラーにする
        if not new_terrain_type.is_walkable and coordinate in self._object_positions:
            raise InvalidPlacementException(f"Cannot change terrain to non-walkable at {coordinate} because an object exists")

        tile.change_terrain(new_terrain_type)
        
        self.add_event(TileTerrainChangedEvent.create(
            aggregate_id=self._spot_id,
            aggregate_type="PhysicalMapAggregate",
            spot_id=self._spot_id,
            coordinate=coordinate,
            new_terrain_type=new_terrain_type.type
        ))

    def _update_tile_walkability(self, coordinate: Coordinate, is_walkable: bool):
        """指定された座標のタイルの通行可能性を更新する"""
        tile = self.get_tile(coordinate)
        tile.override_walkable(is_walkable)
    
    def get_all_objects(self) -> List[WorldObject]:
        return list(self._objects.values())

    def get_all_tiles(self) -> List[Tile]:
        return list(self._tiles.values())

    def add_object(self, obj: WorldObject):
        """マップに新しくオブジェクトを追加する"""
        self._add_object_to_internal_storage(obj)
        
        self.add_event(WorldObjectAddedEvent.create(
            aggregate_id=obj.object_id,
            aggregate_type="WorldObject",
            object_id=obj.object_id,
            coordinate=obj.coordinate
        ))

    def get_objects_in_range(self, center: Coordinate, distance: int) -> List[WorldObject]:
        """指定された座標から一定範囲内のオブジェクトを取得する（マンハッタン距離）"""
        found_objects = []
        for obj in self._objects.values():
            if center.distance_to(obj.coordinate) <= distance:
                found_objects.append(obj)
        return found_objects

    def is_visible(self, from_coord: Coordinate, to_coord: Coordinate) -> bool:
        """指定された2点間に視線が通るか判定する（簡易レイキャスティング）"""
        if from_coord == to_coord:
            return True

        # Bresenham's Line Algorithm の考え方で経由するタイルをチェック
        x0, y0 = from_coord.x, from_coord.y
        x1, y1 = to_coord.x, to_coord.y
        
        dx = abs(x1 - x0)
        dy = abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx - dy

        curr_x, curr_y = x0, y0
        
        while (curr_x, curr_y) != (x1, y1):
            # 現在のタイルが視線を遮るかチェック
            # ただし、開始地点と終了地点は除外して判定するのが一般的（終了地点は見えて良い）
            if (curr_x, curr_y) != (x0, y0):
                if not self.is_walkable(Coordinate(curr_x, curr_y)):
                    return False
            
            e2 = 2 * err
            if e2 > -dy:
                err -= dy
                curr_x += sx
            if e2 < dx:
                err += dx
                curr_y += sy
                
        return True

    def check_and_activate_trigger(self, coordinate: Coordinate, object_id: Optional[WorldObjectId] = None) -> Optional[MapTrigger]:
        """指定された座標のトリガーをチェックし、存在すればイベントを発行してトリガーを返す"""
        tile = self.get_tile(coordinate)
        if tile.trigger:
            self.add_event(TileTriggeredEvent.create(
                aggregate_id=self._spot_id,
                aggregate_type="PhysicalMapAggregate",
                spot_id=self._spot_id,
                coordinate=coordinate,
                trigger_type=tile.trigger.get_trigger_type(),
                object_id=object_id
            ))
            return tile.trigger
        return None
