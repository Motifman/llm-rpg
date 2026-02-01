from typing import List, Dict, Optional, Any
from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.area_trigger_id import AreaTriggerId
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.area_trigger import AreaTrigger
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent, InteractableComponent
from ai_rpg_world.domain.world.entity.map_trigger import MapTrigger
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.enum.world_enum import MovementCapabilityEnum, DirectionEnum
from ai_rpg_world.domain.world.event.map_events import (
    PhysicalMapCreatedEvent,
    WorldObjectStateChangedEvent,
    WorldObjectBlockingChangedEvent,
    WorldObjectMovedEvent,
    WorldObjectAddedEvent,
    TileTerrainChangedEvent,
    TileTriggeredEvent,
    AreaEnteredEvent,
    AreaExitedEvent,
    AreaTriggeredEvent,
    WorldObjectInteractedEvent
)
from ai_rpg_world.domain.world.exception.map_exception import (
    TileNotFoundException, 
    ObjectNotFoundException,
    DuplicateObjectException,
    InvalidPlacementException,
    InvalidMovementException,
    DuplicateAreaTriggerException,
    AreaTriggerNotFoundException,
    NotAnActorException,
    InteractionOutOfRangeException,
    NotFacingTargetException,
    NotInteractableException
)


class PhysicalMapAggregate(AggregateRoot):
    """物理マップ（タイルマップ）の集約"""
    
    def __init__(
        self,
        spot_id: SpotId,
        tiles: Dict[Coordinate, Tile],
        objects: List[WorldObject] = None,
        area_triggers: List[AreaTrigger] = None
    ):
        super().__init__()
        self._spot_id = spot_id
        self._tiles = tiles
        self._objects: Dict[WorldObjectId, WorldObject] = {}
        self._object_positions: Dict[Coordinate, WorldObjectId] = {}
        self._area_triggers: Dict[AreaTriggerId, AreaTrigger] = {t.trigger_id: t for t in (area_triggers or [])}
        
        if objects:
            for obj in objects:
                self._add_object_to_internal_storage(obj)

    @classmethod
    def create(
        cls, 
        spot_id: SpotId, 
        tiles: List[Tile], 
        objects: List[WorldObject] = None,
        area_triggers: List[AreaTrigger] = None
    ) -> "PhysicalMapAggregate":
        tile_dict = {tile.coordinate: tile for tile in tiles}
        aggregate = cls(spot_id, tile_dict, objects, area_triggers)
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
        
        # アクターの場合は能力を取得して配置バリデーションを行う
        capability = None
        if obj.component and isinstance(obj.component, ActorComponent):
            capability = obj.component.capability

        # 座標のバリデーション
        self._validate_placement(obj.coordinate, capability)
        
        # 内部データの更新
        self._objects[obj.object_id] = obj
        self._object_positions[obj.coordinate] = obj.object_id
        
        # オブジェクトによる通行制限を反映
        if obj.is_blocking:
            self._override_tile_walkability(obj.coordinate, False)

    def _validate_placement(self, coordinate: Coordinate, capability: Optional[MovementCapability] = None):
        """指定された座標にオブジェクトを配置可能かチェックする"""
        # 1. タイルが存在するか
        if coordinate not in self._tiles:
            raise InvalidPlacementException(f"Coordinate {coordinate} is out of map bounds")
        
        # 2. 地形的に進入可能か
        tile = self._tiles[coordinate]
        if capability:
            if not tile.terrain_type.can_pass(capability):
                raise InvalidPlacementException(f"Actor with current capabilities cannot enter {tile.terrain_type.type} at {coordinate}")
        else:
            # capabilityが指定されない場合は通常の歩行が可能かチェック
            if not tile.terrain_type.is_walkable:
                raise InvalidPlacementException(f"Cannot place object on non-walkable terrain at {coordinate}")
        
        # 3. 既にオブジェクトが存在しないか
        if coordinate in self._object_positions:
            raise DuplicateObjectException(f"Another object already exists at {coordinate}")

    def is_passable(self, coordinate: Coordinate, capability: MovementCapability) -> bool:
        """指定された座標が特定のアクター能力で通行可能か判定する"""
        try:
            tile = self.get_tile(coordinate)
            # 地形的な通行可能性
            if not tile.terrain_type.can_pass(capability):
                return False
            # オブジェクトによるブロッキング
            if coordinate in self._object_positions:
                obj = self._objects[self._object_positions[coordinate]]
                if obj.is_blocking:
                    if not capability.has_capability(MovementCapabilityEnum.GHOST_WALK):
                        return False
            
            # 地形とオブジェクトの判定をパスすれば通行可能
            return True
        except TileNotFoundException:
            return False

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
        if is_blocking:
            self._override_tile_walkability(obj.coordinate, False)
        else:
            self._reset_tile_walkability(obj.coordinate)
        
        self.add_event(WorldObjectBlockingChangedEvent.create(
            aggregate_id=object_id,
            aggregate_type="WorldObject",
            object_id=object_id,
            is_blocking=is_blocking
        ))

    def move_object(self, object_id: WorldObjectId, new_coordinate: Coordinate, capability: Optional[MovementCapability] = None):
        obj = self.get_object(object_id)
        old_coordinate = obj.coordinate
        
        if old_coordinate == new_coordinate:
            return

        # 移動先のバリデーション
        try:
            self._validate_placement(new_coordinate, capability)
        except (InvalidPlacementException, DuplicateObjectException) as e:
            raise InvalidMovementException(f"Cannot move object to {new_coordinate}: {str(e)}")
            
        # 物理マップの通行可能性（オブジェクトによる上書き）の更新
        if obj.is_blocking:
            self._reset_tile_walkability(old_coordinate)
            self._override_tile_walkability(new_coordinate, False)
            
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

        # エリアトリガーの判定
        self._check_area_triggers(object_id, old_coordinate, new_coordinate)

    def _check_area_triggers(self, object_id: WorldObjectId, old_coordinate: Optional[Coordinate], new_coordinate: Coordinate):
        """進入・退出・滞在判定"""
        for trigger in self._area_triggers.values():
            was_in = trigger.contains(old_coordinate) if old_coordinate else False
            is_in = trigger.contains(new_coordinate)

            if not was_in and is_in:
                # Entering
                self.add_event(AreaEnteredEvent.create(
                    aggregate_id=trigger.trigger_id,
                    aggregate_type="AreaTrigger",
                    trigger_id=trigger.trigger_id,
                    spot_id=self._spot_id,
                    object_id=object_id
                ))
                # 進入時にもトリガーを発火させる（仕様により調整可能）
                self._activate_area_trigger(trigger, object_id)
            elif was_in and not is_in:
                # Exiting
                self.add_event(AreaExitedEvent.create(
                    aggregate_id=trigger.trigger_id,
                    aggregate_type="AreaTrigger",
                    trigger_id=trigger.trigger_id,
                    spot_id=self._spot_id,
                    object_id=object_id
                ))
            elif was_in and is_in:
                # Staying (継続的な効果など)
                self._activate_area_trigger(trigger, object_id)

    def _activate_area_trigger(self, trigger: AreaTrigger, object_id: WorldObjectId):
        """エリアトリガーを発火させる"""
        self.add_event(AreaTriggeredEvent.create(
            aggregate_id=trigger.trigger_id,
            aggregate_type="AreaTrigger",
            trigger_id=trigger.trigger_id,
            spot_id=self._spot_id,
            object_id=object_id,
            trigger_type=trigger.trigger.get_trigger_type()
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

    def _override_tile_walkability(self, coordinate: Coordinate, is_walkable: bool):
        """指定された座標のタイルの通行可能性を上書きする"""
        tile = self.get_tile(coordinate)
        tile.override_walkable(is_walkable)

    def _reset_tile_walkability(self, coordinate: Coordinate):
        """指定された座標のタイルの通行可能性の上書きを解除する"""
        tile = self.get_tile(coordinate)
        tile.reset_walkable()
    
    def get_all_objects(self) -> List[WorldObject]:
        return list(self._objects.values())

    def get_all_tiles(self) -> List[Tile]:
        return list(self._tiles.values())

    def get_all_area_triggers(self) -> List[AreaTrigger]:
        return list(self._area_triggers.values())

    def add_object(self, obj: WorldObject):
        """マップに新しくオブジェクトを追加する"""
        self._add_object_to_internal_storage(obj)
        
        self.add_event(WorldObjectAddedEvent.create(
            aggregate_id=obj.object_id,
            aggregate_type="WorldObject",
            object_id=obj.object_id,
            coordinate=obj.coordinate,
            object_type=obj.object_type
        ))

        # エリアトリガーの判定
        self._check_area_triggers(obj.object_id, None, obj.coordinate)

    def get_objects_in_range(self, center: Coordinate, distance: int) -> List[WorldObject]:
        """指定された座標から一定範囲内のオブジェクトを取得する（マンハッタン距離）"""
        found_objects = []
        for obj in self._objects.values():
            if center.distance_to(obj.coordinate) <= distance:
                found_objects.append(obj)
        return found_objects

    def is_visible(self, from_coord: Coordinate, to_coord: Coordinate) -> bool:
        """指定された座標間が互いに視認可能か判定する（3D Bresenham's Line Algorithm）"""
        if from_coord == to_coord:
            return True

        # 座標がマップ内にあるかチェック
        if from_coord not in self._tiles or to_coord not in self._tiles:
            return False

        # 3D Bresenham (DDAに近い実装)
        x1, y1, z1 = from_coord.x, from_coord.y, from_coord.z
        x2, y2, z2 = to_coord.x, to_coord.y, to_coord.z

        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        dz = abs(z2 - z1)

        xs = 1 if x2 > x1 else -1
        ys = 1 if y2 > y1 else -1
        zs = 1 if z2 > z1 else -1

        # 最大の変化量を基準にする
        if dx >= dy and dx >= dz:
            # x軸メイン
            p1 = 2 * dy - dx
            p2 = 2 * dz - dx
            while x1 != x2:
                x1 += xs
                if p1 >= 0:
                    y1 += ys
                    p1 -= 2 * dx
                if p2 >= 0:
                    z1 += zs
                    p2 -= 2 * dx
                p1 += 2 * dy
                p2 += 2 * dz
                if (x1, y1, z1) == (x2, y2, z2):
                    break
                if self._is_sight_blocked(Coordinate(x1, y1, z1)):
                    return False
        elif dy >= dx and dy >= dz:
            # y軸メイン
            p1 = 2 * dx - dy
            p2 = 2 * dz - dy
            while y1 != y2:
                y1 += ys
                if p1 >= 0:
                    x1 += xs
                    p1 -= 2 * dy
                if p2 >= 0:
                    z1 += zs
                    p2 -= 2 * dy
                p1 += 2 * dx
                p2 += 2 * dz
                if (x1, y1, z1) == (x2, y2, z2):
                    break
                if self._is_sight_blocked(Coordinate(x1, y1, z1)):
                    return False
        else:
            # z軸メイン
            p1 = 2 * dx - dz
            p2 = 2 * dy - dz
            while z1 != z2:
                z1 += zs
                if p1 >= 0:
                    x1 += xs
                    p1 -= 2 * dz
                if p2 >= 0:
                    y1 += ys
                    p2 -= 2 * dz
                p1 += 2 * dx
                p2 += 2 * dy
                if (x1, y1, z1) == (x2, y2, z2):
                    break
                if self._is_sight_blocked(Coordinate(x1, y1, z1)):
                    return False

        return True

    def _is_sight_blocked(self, coordinate: Coordinate) -> bool:
        """指定された座標が視線を遮るか判定する"""
        if coordinate not in self._tiles:
            return False # タイルのない場所（空中など）は透明とみなす

        # 地形の不透明度チェック
        if self._tiles[coordinate].terrain_type.is_opaque:
            return True

        # オブジェクトの視覚遮蔽チェック
        if coordinate in self._object_positions:
            obj = self._objects[self._object_positions[coordinate]]
            if obj.is_blocking_sight:
                return True

        return False

    def move_actor(self, object_id: WorldObjectId, direction: DirectionEnum):
        """アクターを指定された方向に1マス移動させる"""
        obj = self.get_object(object_id)
        if not isinstance(obj.component, ActorComponent):
            raise NotAnActorException(f"Object {object_id} is not an actor")
        
        # 向きを更新
        obj.component.turn(direction)
        
        # 移動先の座標を計算
        curr = obj.coordinate
        new_coord = curr
        if direction == DirectionEnum.NORTH:
            new_coord = Coordinate(curr.x, curr.y - 1, curr.z)
        elif direction == DirectionEnum.SOUTH:
            new_coord = Coordinate(curr.x, curr.y + 1, curr.z)
        elif direction == DirectionEnum.EAST:
            new_coord = Coordinate(curr.x + 1, curr.y, curr.z)
        elif direction == DirectionEnum.WEST:
            new_coord = Coordinate(curr.x - 1, curr.y, curr.z)
        elif direction == DirectionEnum.UP:
            new_coord = Coordinate(curr.x, curr.y, curr.z + 1)
        elif direction == DirectionEnum.DOWN:
            new_coord = Coordinate(curr.x, curr.y, curr.z - 1)
            
        # 移動実行（能力を考慮）
        self.move_object(object_id, new_coord, obj.component.capability)

    def add_area_trigger(self, trigger: AreaTrigger):
        """エリアトリガーを追加する"""
        if trigger.trigger_id in self._area_triggers:
            raise DuplicateAreaTriggerException(f"AreaTrigger with ID {trigger.trigger_id} already exists")
        self._area_triggers[trigger.trigger_id] = trigger

    def remove_area_trigger(self, trigger_id: AreaTriggerId):
        """エリアトリガーを削除する"""
        if trigger_id not in self._area_triggers:
            raise AreaTriggerNotFoundException(f"AreaTrigger with ID {trigger_id} not found")
        del self._area_triggers[trigger_id]

    def interact_with(self, actor_id: WorldObjectId, target_id: WorldObjectId):
        """アクターがターゲットのオブジェクトに対してインタラクションを行う"""
        actor = self.get_object(actor_id)
        target = self.get_object(target_id)

        if not isinstance(actor.component, ActorComponent):
            raise NotAnActorException(f"Object {actor_id} is not an actor")

        # 1. 距離チェック（隣接または同じマス）
        distance = actor.coordinate.distance_to(target.coordinate)
        if distance > 1:
            raise InteractionOutOfRangeException(f"Target {target_id} is too far from actor {actor_id}")

        # 2. 向きチェック（ターゲットが隣接している場合、その方向を向いている必要がある）
        if distance == 1:
            expected_direction = self._get_direction_to(actor.coordinate, target.coordinate)
            if actor.component.direction != expected_direction:
                raise NotFacingTargetException(f"Actor {actor_id} is not facing target {target_id}")

        # 3. インタラクション可能性チェック
        interactable = None
        if isinstance(target.component, InteractableComponent):
            interactable = target.component
        
        if not interactable:
            raise NotInteractableException(f"Target {target_id} has no interactable component")

        # インタラクション成功イベントを発行
        self.add_event(WorldObjectInteractedEvent.create(
            aggregate_id=target_id,
            aggregate_type="WorldObject",
            actor_id=actor_id,
            target_id=target_id,
            interaction_type=interactable.interaction_type,
            data=interactable.data
        ))

    def _get_direction_to(self, from_coord: Coordinate, to_coord: Coordinate) -> DirectionEnum:
        """from_coordからto_coordへの方向を取得する（隣接している前提）"""
        dx = to_coord.x - from_coord.x
        dy = to_coord.y - from_coord.y
        dz = to_coord.z - from_coord.z

        if dz > 0: return DirectionEnum.UP
        if dz < 0: return DirectionEnum.DOWN
        if dx > 0: return DirectionEnum.EAST
        if dx < 0: return DirectionEnum.WEST
        if dy > 0: return DirectionEnum.SOUTH
        if dy < 0: return DirectionEnum.NORTH
        
        # 同じマスの場合は現在のアクターの向きを維持するとみなすか、
        # あるいは特殊な値を返すべきだが、ここでは便宜上SOUTHを返す（呼び出し側で距離0ならスキップも可能）
        return DirectionEnum.SOUTH

    def check_and_activate_trigger(self, coordinate: Coordinate, object_id: Optional[WorldObjectId] = None) -> Optional[MapTrigger]:
        """
        指定された座標のトリガーをチェックし、存在すればイベントを発行してトリガーを返す。
        エリアトリガーシステムに統合されたため、指定座標を含む最初のアクティブなトリガーを返す。
        """
        for trigger in self._area_triggers.values():
            if trigger.contains(coordinate):
                if object_id:
                    self._activate_area_trigger(trigger, object_id)
                return trigger.trigger
        return None
