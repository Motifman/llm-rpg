from typing import List, Dict, Optional, Any
from ai_rpg_world.domain.common.aggregate_root import AggregateRoot
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.area_trigger_id import AreaTriggerId
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.area_trigger import AreaTrigger
from ai_rpg_world.domain.world.entity.location_area import LocationArea
from ai_rpg_world.domain.world.entity.gateway import Gateway
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent, InteractableComponent, HarvestableComponent
from ai_rpg_world.domain.world.entity.map_trigger import MapTrigger
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.enum.world_enum import MovementCapabilityEnum, DirectionEnum, EnvironmentTypeEnum
from ai_rpg_world.domain.world.service.map_geometry_service import MapGeometryService
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.service.weather_effect_service import WeatherEffectService
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
    WorldObjectInteractedEvent,
    LocationEnteredEvent,
    LocationExitedEvent,
    GatewayTriggeredEvent
)
from ai_rpg_world.domain.world.event.harvest_events import (
    HarvestStartedEvent,
    HarvestCancelledEvent,
    HarvestCompletedEvent
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
    NotInteractableException,
    SameCoordinateDirectionException,
    DuplicateLocationAreaException,
    LocationAreaNotFoundException,
    DuplicateGatewayException,
    GatewayNotFoundException,
    ActorBusyException
)
from ai_rpg_world.domain.world.exception.harvest_exception import (
    NotHarvestableException,
    ResourceExhaustedException,
    HarvestInProgressException,
    HarvestNotStartedException
)
from ai_rpg_world.domain.common.value_object import WorldTick


class PhysicalMapAggregate(AggregateRoot):
    """物理マップ（タイルマップ）の集約"""
    
    def __init__(
        self,
        spot_id: SpotId,
        tiles: Dict[Coordinate, Tile],
        objects: List[WorldObject] = None,
        area_triggers: List[AreaTrigger] = None,
        location_areas: List[LocationArea] = None,
        gateways: List[Gateway] = None,
        environment_type: EnvironmentTypeEnum = EnvironmentTypeEnum.OUTDOOR
    ):
        super().__init__()
        self._spot_id = spot_id
        self._tiles = tiles
        self._objects: Dict[WorldObjectId, WorldObject] = {}
        self._object_positions: Dict[Coordinate, List[WorldObjectId]] = {}
        self._area_triggers: Dict[AreaTriggerId, AreaTrigger] = {t.trigger_id: t for t in (area_triggers or [])}
        self._location_areas: Dict[LocationAreaId, LocationArea] = {l.location_id: l for l in (location_areas or [])}
        self._gateways: Dict[GatewayId, Gateway] = {g.gateway_id: g for g in (gateways or [])}
        self._environment_type = environment_type
        self._weather_state = WeatherState.clear()
        
        if objects:
            for obj in objects:
                self._add_object_to_internal_storage(obj)

    @classmethod
    def create(
        cls, 
        spot_id: SpotId, 
        tiles: List[Tile], 
        objects: List[WorldObject] = None,
        area_triggers: List[AreaTrigger] = None,
        location_areas: List[LocationArea] = None,
        gateways: List[Gateway] = None
    ) -> "PhysicalMapAggregate":
        tile_dict = {tile.coordinate: tile for tile in tiles}
        aggregate = cls(spot_id, tile_dict, objects, area_triggers, location_areas, gateways)
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
        
        # 座標のバリデーション（ブロッキング設定を考慮）
        self._validate_placement(obj.coordinate, obj.is_blocking, obj.capability)
        
        # 内部データの更新
        self._objects[obj.object_id] = obj
        if obj.coordinate not in self._object_positions:
            self._object_positions[obj.coordinate] = []
        self._object_positions[obj.coordinate].append(obj.object_id)
        
        # オブジェクトによる通行制限を反映
        if obj.is_blocking:
            self._override_tile_walkability(obj.coordinate, False)

    def get_actor(self, object_id: WorldObjectId) -> WorldObject:
        """指定されたIDのオブジェクトを取得し、アクターであることを保証する"""
        obj = self.get_object(object_id)
        if not obj.is_actor:
            raise NotAnActorException(f"Object {object_id} is not an actor")
        return obj

    def _validate_placement(self, coordinate: Coordinate, is_blocking: bool, capability: Optional[MovementCapability] = None, exclude_object_id: Optional[WorldObjectId] = None):
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
        
        # 3. 既存オブジェクトとの衝突チェック（重なりルール）
        if coordinate in self._object_positions:
            existing_ids = [oid for oid in self._object_positions[coordinate] if oid != exclude_object_id]
            if existing_ids:
                existing_objects = [self._objects[oid] for oid in existing_ids]
                
                # ルール: 配置対象がブロッキングなら、既に何かあれば不可
                if is_blocking:
                    raise DuplicateObjectException(f"Cannot place blocking object at {coordinate} because other objects already exist")
                
                # ルール: 配置対象が非ブロッキングなら、既存にブロッキングがあれば不可
                if any(o.is_blocking for o in existing_objects):
                    raise InvalidPlacementException(f"Cannot enter {coordinate} because it is blocked by another object")

    def set_weather(self, weather_state: WeatherState):
        """天候状態を設定する。屋内や地下の場合は常に晴れとして扱う。"""
        if self._environment_type == EnvironmentTypeEnum.OUTDOOR:
            self._weather_state = weather_state
        else:
            self._weather_state = WeatherState.clear()

    def is_passable(self, coordinate: Coordinate, capability: MovementCapability, exclude_object_id: Optional[WorldObjectId] = None) -> bool:
        """指定された座標が特定のアクター能力で通行可能か判定する"""
        try:
            tile = self.get_tile(coordinate)
            # 地形的な通行可能性
            if not tile.terrain_type.can_pass(capability):
                return False
            # オブジェクトによるブロッキング
            if coordinate in self._object_positions:
                # 指定されたアクター以外のブロッキングオブジェクトをチェック
                existing_objects = [
                    self._objects[oid] for oid in self._object_positions[coordinate] 
                    if oid != exclude_object_id
                ]
                if any(o.is_blocking for o in existing_objects):
                    if not capability.has_capability(MovementCapabilityEnum.GHOST_WALK):
                        return False
            
            # 地形とオブジェクトの判定をパスすれば通行可能
            return True
        except TileNotFoundException:
            return False

    def get_movement_cost(self, coordinate: Coordinate, capability: MovementCapability, exclude_object_id: Optional[WorldObjectId] = None) -> float:
        """指定された座標の移動コストを計算する。通行不可の場合は無限大を返す。"""
        if not self.is_passable(coordinate, capability, exclude_object_id=exclude_object_id):
            return float('inf')
        
        tile = self.get_tile(coordinate)
        base_cost = tile.terrain_type.calculate_cost(capability).value
        
        # 天候によるコスト増加
        multiplier = WeatherEffectService.calculate_movement_cost_multiplier(
            self._weather_state, 
            self._environment_type
        )
        return base_cost * multiplier

    @property
    def spot_id(self) -> SpotId:
        return self._spot_id

    @property
    def actors(self) -> List[WorldObject]:
        """マップ上の全アクターを取得する"""
        return [obj for obj in self._objects.values() if obj.is_actor]

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
        
        # ブロッキング状態を切り替える前に衝突チェックが必要（非ブロッキング->ブロッキングの場合）
        if is_blocking:
            # 自分以外にオブジェクトがあればブロッキングになれない
            if len(self._object_positions.get(obj.coordinate, [])) > 1:
                 raise DuplicateObjectException(f"Cannot set object {object_id} to blocking because other objects share the same coordinate")
            
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

    def move_object(self, object_id: WorldObjectId, new_coordinate: Coordinate, current_tick: WorldTick, capability: Optional[MovementCapability] = None):
        obj = self.get_object(object_id)
        
        # 1. ビジー状態のチェック
        if obj.is_busy(current_tick):
            raise ActorBusyException(f"Object {object_id} is busy until {obj.busy_until}")

        old_coordinate = obj.coordinate
        
        if old_coordinate == new_coordinate:
            return

        # 移動先のバリデーション
        # 移動能力の解決（指定がない場合はオブジェクトの能力、それもなければ通常歩行）
        actual_capability = capability or obj.capability or MovementCapability.normal_walk()
        
        try:
            self._validate_placement(new_coordinate, obj.is_blocking, actual_capability, exclude_object_id=object_id)
        except (InvalidPlacementException, DuplicateObjectException) as e:
            raise InvalidMovementException(f"Cannot move object to {new_coordinate}: {str(e)}")
            
        # 2. 移動にかかるティック数を計算（コストに基づく）
        # 移動先タイルのコストを取得
        cost = self.get_movement_cost(new_coordinate, actual_capability, exclude_object_id=object_id)
        
        # 基本倍率（例：1.0コスト = 1ティック）
        # 小数点以下は切り上げ
        import math
        travel_ticks = max(1, math.ceil(cost))
        
        # 3. 状態の更新
        # 物理マップの通行可能性（オブジェクトによる上書き）の更新
        if obj.is_blocking:
            self._reset_tile_walkability(old_coordinate)
            self._override_tile_walkability(new_coordinate, False)
            
        # 位置管理の更新
        self._object_positions[old_coordinate].remove(object_id)
        if not self._object_positions[old_coordinate]:
            del self._object_positions[old_coordinate]
            
        if new_coordinate not in self._object_positions:
            self._object_positions[new_coordinate] = []
        self._object_positions[new_coordinate].append(object_id)
        
        # オブジェクトの座標更新とビジー設定
        obj.move_to(new_coordinate)
        obj.set_busy(current_tick.add_duration(travel_ticks))
        
        self.add_event(WorldObjectMovedEvent.create(
            aggregate_id=object_id,
            aggregate_type="WorldObject",
            object_id=object_id,
            from_coordinate=old_coordinate,
            to_coordinate=new_coordinate,
            arrival_tick=obj.busy_until
        ))

        # エリアトリガーの判定
        self._check_area_triggers(object_id, old_coordinate, new_coordinate)

    def _check_area_triggers(self, object_id: WorldObjectId, old_coordinate: Optional[Coordinate], new_coordinate: Coordinate):
        """進入・退出・滞在判定"""
        # 1. AreaTriggerの判定
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

        # 2. LocationAreaの判定
        for loc in self._location_areas.values():
            was_in = loc.contains(old_coordinate) if old_coordinate else False
            is_in = loc.contains(new_coordinate)

            if not was_in and is_in:
                # Entering a location area - send detailed info
                self.add_event(LocationEnteredEvent.create(
                    aggregate_id=loc.location_id,
                    aggregate_type="LocationArea",
                    location_id=loc.location_id,
                    spot_id=self._spot_id,
                    object_id=object_id,
                    name=loc.name,
                    description=loc.description
                ))
            elif was_in and not is_in:
                # Exiting a location area
                self.add_event(LocationExitedEvent.create(
                    aggregate_id=loc.location_id,
                    aggregate_type="LocationArea",
                    location_id=loc.location_id,
                    spot_id=self._spot_id,
                    object_id=object_id
                ))

        # 3. Gatewayの判定
        for gateway in self._gateways.values():
            was_in = gateway.contains(old_coordinate) if old_coordinate else False
            is_in = gateway.contains(new_coordinate)

            if not was_in and is_in:
                # Entering a gateway area triggers the transition
                self.add_event(GatewayTriggeredEvent.create(
                    aggregate_id=gateway.gateway_id,
                    aggregate_type="Gateway",
                    gateway_id=gateway.gateway_id,
                    spot_id=self._spot_id,
                    object_id=object_id,
                    target_spot_id=gateway.target_spot_id,
                    landing_coordinate=gateway.landing_coordinate
                ))

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

    def get_all_location_areas(self) -> List[LocationArea]:
        return list(self._location_areas.values())

    def get_all_gateways(self) -> List[Gateway]:
        return list(self._gateways.values())

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
        # 天候による視界減衰
        reduction = WeatherEffectService.calculate_vision_reduction(
            self._weather_state,
            self._environment_type
        )
        effective_distance = max(0, distance - reduction)
        
        # 天候による絶対的な最大視界制限
        max_dist = WeatherEffectService.get_max_vision_distance(
            self._weather_state,
            self._environment_type
        )
        effective_distance = min(effective_distance, max_dist)
        
        found_objects = []
        for obj in self._objects.values():
            if center.distance_to(obj.coordinate) <= effective_distance:
                found_objects.append(obj)
        return found_objects

    def is_visible(self, from_coord: Coordinate, to_coord: Coordinate) -> bool:
        """指定された座標間が互いに視認可能か判定する"""
        # 座標がマップ内にあるかチェック（元の実装の動作を維持）
        if from_coord not in self._tiles or to_coord not in self._tiles:
            return False
            
        # 天候による最大視界制限チェック
        max_dist = WeatherEffectService.get_max_vision_distance(
            self._weather_state,
            self._environment_type
        )
        if from_coord.distance_to(to_coord) > max_dist:
            return False

        return MapGeometryService.is_visible(from_coord, to_coord, self)

    def is_sight_blocked(self, coordinate: Coordinate) -> bool:
        """指定された座標が視線を遮るか判定する（VisibilityMapプロトコルの実装）"""
        if coordinate not in self._tiles:
            return False # タイルのない場所（空中など）は透明とみなす

        # 地形の不透明度チェック
        if self._tiles[coordinate].terrain_type.is_opaque:
            return True

        # オブジェクトの視覚遮蔽チェック
        if coordinate in self._object_positions:
            existing_objects = [self._objects[oid] for oid in self._object_positions[coordinate]]
            if any(obj.is_blocking_sight for obj in existing_objects):
                return True

        return False

    def remove_object(self, object_id: WorldObjectId):
        """オブジェクトをマップから削除する"""
        obj = self.get_object(object_id)
        coord = obj.coordinate
        
        if obj.is_blocking:
            self._reset_tile_walkability(coord)
            
        self._object_positions[coord].remove(object_id)
        if not self._object_positions[coord]:
            del self._object_positions[coord]
            
        del self._objects[object_id]

    def move_actor(self, object_id: WorldObjectId, direction: DirectionEnum, current_tick: WorldTick):
        """アクターを指定された方向に1マス移動させる"""
        actor = self.get_actor(object_id)
        
        # 向きを更新
        actor.turn(direction)
        
        # 移動先の座標を計算
        new_coord = actor.coordinate.neighbor(direction)
            
        # 移動実行（能力を考慮）
        self.move_object(object_id, new_coord, current_tick, actor.capability)

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

    def add_location_area(self, location_area: LocationArea):
        """ロケーションエリアを追加する"""
        if location_area.location_id in self._location_areas:
            raise DuplicateLocationAreaException(f"LocationArea with ID {location_area.location_id} already exists")
        self._location_areas[location_area.location_id] = location_area

    def remove_location_area(self, location_id: LocationAreaId):
        """ロケーションエリアを削除する"""
        if location_id not in self._location_areas:
            raise LocationAreaNotFoundException(f"LocationArea with ID {location_id} not found")
        del self._location_areas[location_id]

    def add_gateway(self, gateway: Gateway):
        """ゲートウェイを追加する"""
        if gateway.gateway_id in self._gateways:
            raise DuplicateGatewayException(f"Gateway with ID {gateway.gateway_id} already exists")
        self._gateways[gateway.gateway_id] = gateway

    def remove_gateway(self, gateway_id: GatewayId):
        """ゲートウェイを削除する"""
        if gateway_id not in self._gateways:
            raise GatewayNotFoundException(f"Gateway with ID {gateway_id} not found")
        del self._gateways[gateway_id]

    def get_location_area(self, location_id: LocationAreaId) -> LocationArea:
        if location_id not in self._location_areas:
            raise LocationAreaNotFoundException(f"LocationArea with ID {location_id} not found")
        return self._location_areas[location_id]

    def get_gateway(self, gateway_id: GatewayId) -> Gateway:
        if gateway_id not in self._gateways:
            raise GatewayNotFoundException(f"Gateway with ID {gateway_id} not found")
        return self._gateways[gateway_id]

    def perform_action(self, object_id: WorldObjectId, duration: int, current_tick: WorldTick):
        """オブジェクトに時間のかかるアクションを実行させる"""
        obj = self.get_object(object_id)
        
        if obj.is_busy(current_tick):
            raise ActorBusyException(f"Object {object_id} is busy until {obj.busy_until}")
            
        if duration < 0:
            raise ValueError(f"Duration cannot be negative: {duration}")
            
        obj.set_busy(current_tick.add_duration(duration))

    def interact_with(self, actor_id: WorldObjectId, target_id: WorldObjectId, current_tick: WorldTick):
        """アクターがターゲットのオブジェクトに対してインタラクションを行う"""
        actor = self.get_actor(actor_id)
        target = self.get_object(target_id)

        # 0. ビジー状態のチェック
        if actor.is_busy(current_tick):
            raise ActorBusyException(f"Actor {actor_id} is busy until {actor.busy_until}")

        # 1. 距離チェック（隣接または同じマス）
        distance = actor.coordinate.distance_to(target.coordinate)
        if distance > 1:
            raise InteractionOutOfRangeException(f"Target {target_id} is too far from actor {actor_id}")

        # 2. 向きチェック（ターゲットが隣接している場合、その方向を向いている必要がある）
        if distance == 1:
            expected_direction = actor.coordinate.direction_to(target.coordinate)
            if actor.direction != expected_direction:
                raise NotFacingTargetException(f"Actor {actor_id} is not facing target {target_id}")

        # 3. インタラクション可能性チェック
        interaction_type = target.interaction_type
        if not interaction_type:
            raise NotInteractableException(f"Target {target_id} is not interactable")

        # インタラクション成功イベントを発行
        self.add_event(WorldObjectInteractedEvent.create(
            aggregate_id=target_id,
            aggregate_type="WorldObject",
            actor_id=actor_id,
            target_id=target_id,
            interaction_type=interaction_type,
            data=target.interaction_data
        ))

        # アクターをビジー状態にする
        duration = target.interaction_duration
        actor.set_busy(current_tick.add_duration(duration))

    def start_resource_harvest(self, actor_id: WorldObjectId, target_id: WorldObjectId, current_tick: WorldTick):
        """資源の採取を開始する"""
        actor = self.get_actor(actor_id)
        target = self.get_object(target_id)

        # 1. 距離と向きのチェック
        distance = actor.coordinate.distance_to(target.coordinate)
        if distance > 1:
            raise InteractionOutOfRangeException(f"Target {target_id} is too far from actor {actor_id}")
        if distance == 1:
            expected_direction = actor.coordinate.direction_to(target.coordinate)
            if actor.direction != expected_direction:
                raise NotFacingTargetException(f"Actor {actor_id} is not facing target {target_id}")

        # 2. HarvestableComponentのチェック
        if not isinstance(target.component, HarvestableComponent):
            raise NotHarvestableException(f"Object {target_id} is not harvestable")

        # 3. コンポーネントの採取開始（状態更新と終了時間の取得）
        finish_tick = target.component.start_harvest(actor_id, current_tick)

        # 4. アクターをビジー状態にする
        actor.set_busy(finish_tick)

        # 5. イベント発行
        self.add_event(HarvestStartedEvent.create(
            aggregate_id=target_id,
            aggregate_type="WorldObject",
            actor_id=actor_id,
            target_id=target_id,
            finish_tick=finish_tick
        ))

    def finish_resource_harvest(self, actor_id: WorldObjectId, target_id: WorldObjectId, current_tick: WorldTick):
        """資源の採取を完了させる"""
        actor = self.get_actor(actor_id)
        target = self.get_object(target_id)

        if not isinstance(target.component, HarvestableComponent):
            raise NotHarvestableException(f"Object {target_id} is not harvestable")

        # コンポーネントの採取完了処理
        loot_table_id = target.component.loot_table_id
        success = target.component.finish_harvest(actor_id, current_tick)

        if success:
            # アクターのビジー状態を解除（念のため、現在のティックに合わせる）
            actor.clear_busy()

            # イベント発行
            self.add_event(HarvestCompletedEvent.create(
                aggregate_id=target_id,
                aggregate_type="WorldObject",
                actor_id=actor_id,
                target_id=target_id,
                loot_table_id=loot_table_id
            ))

    def cancel_resource_harvest(self, actor_id: WorldObjectId, target_id: WorldObjectId, reason: str = "cancelled"):
        """資源の採取を中断する"""
        actor = self.get_actor(actor_id)
        target = self.get_object(target_id)

        if not isinstance(target.component, HarvestableComponent):
            raise NotHarvestableException(f"Object {target_id} is not harvestable")

        # コンポーネントの採取中断処理
        target.component.cancel_harvest(actor_id)

        # アクターのビジー状態を解除
        actor.clear_busy()

        # イベント発行
        self.add_event(HarvestCancelledEvent.create(
            aggregate_id=target_id,
            aggregate_type="WorldObject",
            actor_id=actor_id,
            target_id=target_id,
            reason=reason
        ))

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
