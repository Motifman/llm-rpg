import pytest
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.enum.world_enum import (
    ObjectTypeEnum,
    TerrainTypeEnum,
    TriggerTypeEnum,
    DirectionEnum,
    MovementCapabilityEnum,
    EnvironmentTypeEnum,
    InteractionTypeEnum,
)
from ai_rpg_world.domain.world.exception.map_exception import (
    TileNotFoundException,
    ObjectNotFoundException,
    DuplicateObjectException,
    InvalidPlacementException,
    InvalidMovementException,
    NotAnActorException,
    ActorBusyException,
    DuplicateAreaTriggerException,
    AreaTriggerNotFoundException,
    InteractionOutOfRangeException,
    NotFacingTargetException,
    NotInteractableException,
    SameCoordinateDirectionException,
    LockedDoorException,
    ChestClosedException,
    NotAChestException,
    ItemNotInChestException,
)
from ai_rpg_world.domain.world.value_object.area_trigger_id import AreaTriggerId
from ai_rpg_world.domain.world.value_object.area import PointArea, RectArea
from ai_rpg_world.domain.world.entity.area_trigger import AreaTrigger
from ai_rpg_world.domain.world.entity.world_object_component import (
    ActorComponent,
    AutonomousBehaviorComponent,
    InteractableComponent,
    ChestComponent,
    DoorComponent,
)
from ai_rpg_world.domain.world.event.map_events import (
    PhysicalMapCreatedEvent,
    WorldObjectMovedEvent,
    WorldObjectBlockingChangedEvent,
    WorldObjectAddedEvent,
    TileTerrainChangedEvent,
    TileTriggeredEvent,
    AreaEnteredEvent,
    AreaExitedEvent,
    AreaTriggeredEvent,
    WorldObjectInteractedEvent,
    ItemStoredInChestEvent,
    ItemTakenFromChestEvent,
)
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.world.value_object.pack_id import PackId
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.entity.map_trigger import WarpTrigger, DamageTrigger
from ai_rpg_world.domain.common.value_object import WorldTick


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

        def test_add_actor_with_swim_capability_on_water(self, spot_id):
            # Given
            tiles = [Tile(Coordinate(0, 0), TerrainType.water())]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            
            swim_actor = ActorComponent(capability=MovementCapability(frozenset({MovementCapabilityEnum.SWIM})))
            obj = WorldObject(WorldObjectId(1), Coordinate(0, 0), ObjectTypeEnum.PLAYER, component=swim_actor)
            
            # When
            aggregate.add_object(obj)
            
            # Then
            assert aggregate.get_object(WorldObjectId(1)).coordinate == Coordinate(0, 0)

        def test_add_normal_actor_on_water_raises_error(self, spot_id):
            # Given
            tiles = [Tile(Coordinate(0, 0), TerrainType.water())]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            
            normal_actor = ActorComponent(capability=MovementCapability.normal_walk())
            obj = WorldObject(WorldObjectId(1), Coordinate(0, 0), ObjectTypeEnum.PLAYER, component=normal_actor)
            
            # When & Then
            with pytest.raises(InvalidPlacementException):
                aggregate.add_object(obj)

        def test_add_object_event_contains_all_fields(self, spot_id):
            # Given
            tiles = [Tile(Coordinate(0, 0), TerrainType.road())]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            aggregate.clear_events()
            
            obj_id = WorldObjectId(1)
            coord = Coordinate(0, 0)
            obj_type = ObjectTypeEnum.SIGN
            obj = WorldObject(obj_id, coord, obj_type)
            
            # When
            aggregate.add_object(obj)
            
            # Then
            events = aggregate.get_events()
            assert len(events) == 1
            event = events[0]
            assert isinstance(event, WorldObjectAddedEvent)
            assert event.aggregate_id == obj_id
            assert event.aggregate_type == "WorldObject"
            assert event.object_id == obj_id
            assert event.coordinate == coord
            assert event.object_type == obj_type
            assert hasattr(event, 'event_id')
            assert hasattr(event, 'occurred_at')

        def test_add_object_triggers_area_trigger(self, aggregate):
            # Given
            warp = WarpTrigger(SpotId(2), Coordinate(10, 10, 0))
            area_trigger = AreaTrigger(AreaTriggerId(1), RectArea(1, 1, 1, 1, 0, 0), warp)
            aggregate.add_area_trigger(area_trigger)
            aggregate.clear_events()
            
            obj_id = WorldObjectId(10)
            coord = Coordinate(1, 1, 0)
            obj = WorldObject(obj_id, coord, ObjectTypeEnum.PLAYER)
            
            # When
            aggregate.add_object(obj)
            
            # Then
            events = aggregate.get_events()
            assert any(isinstance(e, AreaEnteredEvent) for e in events)
            assert any(isinstance(e, AreaTriggeredEvent) for e in events)

    class TestCapabilityMovement:
        def test_ghost_can_move_through_wall(self, spot_id):
            # Given
            tiles = [
                Tile(Coordinate(0, 0), TerrainType.road()),
                Tile(Coordinate(1, 1), TerrainType.wall())
            ]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            obj_id = WorldObjectId(1)
            obj = WorldObject(obj_id, Coordinate(0, 0), ObjectTypeEnum.SIGN)
            aggregate.add_object(obj)
            
            ghost_cap = MovementCapability.ghost()
            
            # When
            aggregate.move_object(obj_id, Coordinate(1, 1), WorldTick(10), ghost_cap)
            
            # Then
            assert aggregate.get_object(obj_id).coordinate == Coordinate(1, 1)

        def test_normal_cannot_move_through_wall(self, spot_id):
            # Given
            tiles = [
                Tile(Coordinate(0, 0), TerrainType.road()),
                Tile(Coordinate(1, 1), TerrainType.wall())
            ]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            obj_id = WorldObjectId(1)
            obj = WorldObject(obj_id, Coordinate(0, 0), ObjectTypeEnum.SIGN)
            aggregate.add_object(obj)
            
            normal_cap = MovementCapability.normal_walk()
            
            # When & Then
            with pytest.raises(InvalidMovementException):
                aggregate.move_object(obj_id, Coordinate(1, 1), WorldTick(10), normal_cap)

        def test_is_passable_checks_object_blocking(self, aggregate):
            # Given
            obj_id = WorldObjectId(1)
            coord = Coordinate(1, 1)
            obj = WorldObject(obj_id, coord, ObjectTypeEnum.CHEST, is_blocking=True)
            aggregate.add_object(obj)
            
            normal_cap = MovementCapability.normal_walk()
            ghost_cap = MovementCapability.ghost()
            
            # Then
            assert aggregate.is_passable(coord, normal_cap) is False
            assert aggregate.is_passable(coord, ghost_cap) is True

        def test_terrain_calculate_cost_with_speed_modifier(self):
            terrain = TerrainType.swamp()
            normal_cap = MovementCapability.normal_walk()
            slow_cap = MovementCapability.normal_walk().with_speed_modifier(0.5)
            fast_cap = MovementCapability.normal_walk().with_speed_modifier(2.0)
            
            # Swamp base cost is 5.0
            assert terrain.calculate_cost(normal_cap).value == 5.0
            assert terrain.calculate_cost(slow_cap).value == 10.0
            assert terrain.calculate_cost(fast_cap).value == 2.5

        def test_move_actor_helper(self, spot_id):
            # Given
            tiles = [Tile(Coordinate(x, y, 0), TerrainType.road()) for x in range(3) for y in range(3)]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            
            actor_comp = ActorComponent(direction=DirectionEnum.SOUTH)
            obj_id = WorldObjectId(1)
            aggregate.add_object(WorldObject(obj_id, Coordinate(1, 1, 0), ObjectTypeEnum.PLAYER, component=actor_comp))
            
            # When
            aggregate.move_actor(obj_id, DirectionEnum.EAST, WorldTick(10))
            
            # Then
            assert aggregate.get_object(obj_id).coordinate == Coordinate(2, 1, 0)
            assert aggregate.get_object(obj_id).component.direction == DirectionEnum.EAST

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
            current_tick = WorldTick(10)
            
            # When
            aggregate.move_object(obj_id, end_coord, current_tick)
            
            # Then
            assert aggregate.get_object(obj_id).coordinate == end_coord
            assert aggregate.is_walkable(start_coord) is True
            assert aggregate.is_walkable(end_coord) is False
            
            # ビジー状態の確認
            assert obj.is_busy(current_tick) is True
            # Roadのコストは1.0なので、10 + 1 = 11になるはず
            assert obj.busy_until == WorldTick(11)

            events = aggregate.get_events()
            assert any(isinstance(e, WorldObjectMovedEvent) for e in events)
            move_event = [e for e in events if isinstance(e, WorldObjectMovedEvent)][0]
            assert move_event.arrival_tick == WorldTick(11)

        def test_move_fails_when_busy(self, aggregate):
            # Given
            obj_id = WorldObjectId(1)
            obj = WorldObject(obj_id, Coordinate(0, 0), ObjectTypeEnum.SIGN, busy_until=WorldTick(20))
            aggregate._add_object_to_internal_storage(obj)
            
            # When & Then
            with pytest.raises(ActorBusyException):
                aggregate.move_object(obj_id, Coordinate(1, 1), WorldTick(15))

        def test_move_cost_affects_busy_duration(self, spot_id):
            # Given: Swamp (cost 5.0)
            tiles = [
                Tile(Coordinate(0, 0), TerrainType.road()),
                Tile(Coordinate(0, 1), TerrainType.swamp())
            ]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            obj_id = WorldObjectId(1)
            obj = WorldObject(obj_id, Coordinate(0, 0), ObjectTypeEnum.PLAYER)
            aggregate.add_object(obj)
            current_tick = WorldTick(10)
            
            # When
            aggregate.move_object(obj_id, Coordinate(0, 1), current_tick)
            
            # Then
            # Swamp cost 5.0 -> 10 + 5 = 15
            assert obj.busy_until == WorldTick(15)

        def test_move_to_same_position_does_nothing(self, aggregate):
            obj_id = WorldObjectId(1)
            coord = Coordinate(0, 0)
            obj = WorldObject(obj_id, coord, ObjectTypeEnum.SIGN)
            aggregate._add_object_to_internal_storage(obj)
            aggregate.clear_events()
            
            aggregate.move_object(obj_id, coord, WorldTick(10))
            
            assert len(aggregate.get_events()) == 0

        def test_move_to_occupied_tile_raises_error(self, aggregate):
            obj1 = WorldObject(WorldObjectId(1), Coordinate(0, 0), ObjectTypeEnum.CHEST)
            obj2 = WorldObject(WorldObjectId(2), Coordinate(1, 1), ObjectTypeEnum.CHEST)
            aggregate._add_object_to_internal_storage(obj1)
            aggregate._add_object_to_internal_storage(obj2)
            
            with pytest.raises(InvalidMovementException):
                aggregate.move_object(WorldObjectId(1), Coordinate(1, 1), WorldTick(10))

        def test_move_to_wall_raises_error(self, spot_id):
            tiles = [
                Tile(Coordinate(0, 0), TerrainType.road()),
                Tile(Coordinate(1, 1), TerrainType.wall())
            ]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            obj_id = WorldObjectId(1)
            aggregate._add_object_to_internal_storage(WorldObject(obj_id, Coordinate(0, 0), ObjectTypeEnum.CHEST))
            
            with pytest.raises(InvalidMovementException):
                aggregate.move_object(obj_id, Coordinate(1, 1), WorldTick(10))

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

        def test_visible_through_water_but_impassable(self, spot_id):
            # Given
            tiles = [
                Tile(Coordinate(0, 0), TerrainType.road()),
                Tile(Coordinate(1, 1), TerrainType.water()),
                Tile(Coordinate(2, 2), TerrainType.road())
            ]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            
            # When & Then
            # 水は通行不可（通常歩行）だが、透明なので視線は通る
            assert aggregate.is_visible(Coordinate(0, 0), Coordinate(2, 2)) is True
            assert aggregate.is_passable(Coordinate(1, 1), MovementCapability.normal_walk()) is False

        def test_visible_through_glass_wall(self, spot_id):
            # Given
            tiles = [
                Tile(Coordinate(0, 0), TerrainType.road()),
                Tile(Coordinate(1, 1), TerrainType.glass_wall()),
                Tile(Coordinate(2, 2), TerrainType.road())
            ]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            
            # When & Then
            assert aggregate.is_visible(Coordinate(0, 0), Coordinate(2, 2)) is True

        def test_not_visible_blocked_by_object(self, aggregate):
            # Given
            obj = WorldObject(WorldObjectId(1), Coordinate(1, 1), ObjectTypeEnum.SIGN, is_blocking_sight=True)
            aggregate.add_object(obj)
            
            # When & Then
            assert aggregate.is_visible(Coordinate(0, 0), Coordinate(2, 2)) is False

        def test_visible_blocked_by_non_sight_blocking_object(self, aggregate):
            # Given
            # 通行は遮るが視界は遮らないオブジェクト（例：低い柵）
            obj = WorldObject(WorldObjectId(1), Coordinate(1, 1), ObjectTypeEnum.SIGN, is_blocking=True, is_blocking_sight=False)
            aggregate.add_object(obj)
            
            # When & Then
            assert aggregate.is_visible(Coordinate(0, 0), Coordinate(2, 2)) is True
            assert aggregate.is_walkable(Coordinate(1, 1)) is False

        def test_visible_after_object_blocking_sight_disabled(self, aggregate):
            # Given
            obj = WorldObject(WorldObjectId(1), Coordinate(1, 1), ObjectTypeEnum.DOOR, is_blocking_sight=True)
            aggregate.add_object(obj)
            assert aggregate.is_visible(Coordinate(0, 0), Coordinate(2, 2)) is False
            
            # When
            aggregate.get_object(WorldObjectId(1)).set_blocking_sight(False)
            
            # Then
            assert aggregate.is_visible(Coordinate(0, 0), Coordinate(2, 2)) is True

        def test_3d_vision_across_floors(self, spot_id):
            # Given: 吹き抜けのような構造
            tiles = [
                Tile(Coordinate(0, 0, 0), TerrainType.road()),
                Tile(Coordinate(1, 1, 1), TerrainType.road()), # 空中の足場
                Tile(Coordinate(2, 2, 2), TerrainType.road())
            ]
            # 間の空間を埋める（透明な空気タイルがない場合は適宜作成するが、ここでは単純化）
            # マップ内に存在しない座標は現在Falseを返す仕様なので、経由地点もタイルが必要
            tiles.extend([
                Tile(Coordinate(0, 0, 1), TerrainType.road()),
                Tile(Coordinate(1, 1, 0), TerrainType.road()),
                Tile(Coordinate(1, 1, 2), TerrainType.road()),
                Tile(Coordinate(2, 2, 0), TerrainType.road()),
                Tile(Coordinate(2, 2, 1), TerrainType.road()),
                Tile(Coordinate(0, 0, 2), TerrainType.road()),
            ])
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            
            # When & Then
            assert aggregate.is_visible(Coordinate(0, 0, 0), Coordinate(2, 2, 2)) is True

        def test_3d_vision_blocked_by_floor(self, spot_id):
            # Given: 1階から3階を見ようとするが、2階に床（不透明な壁）がある
            tiles = [
                Tile(Coordinate(0, 0, 0), TerrainType.road()),
                Tile(Coordinate(1, 1, 1), TerrainType.wall()), # 遮蔽物
                Tile(Coordinate(2, 2, 2), TerrainType.road())
            ]
            tiles.extend([
                Tile(Coordinate(0, 0, 1), TerrainType.road()),
                Tile(Coordinate(2, 2, 1), TerrainType.road()),
            ])
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            
            # When & Then
            assert aggregate.is_visible(Coordinate(0, 0, 0), Coordinate(2, 2, 2)) is False

        def test_vision_with_out_of_bounds_coordinate(self, aggregate):
            # When & Then
            # マップ外の座標を含む場合はFalse
            assert aggregate.is_visible(Coordinate(0, 0, 0), Coordinate(99, 99, 0)) is False
            assert aggregate.is_visible(Coordinate(99, 99, 0), Coordinate(0, 0, 0)) is False

    class TestTriggers:
        def test_area_trigger_activation_on_move(self, aggregate):
            # Given
            target_spot = SpotId(2)
            target_coord = Coordinate(10, 10, 0)
            warp = WarpTrigger(target_spot, target_coord)
            area_trigger = AreaTrigger(AreaTriggerId(1), RectArea(1, 1, 1, 1, 0, 0), warp)
            aggregate.add_area_trigger(area_trigger)
            
            obj_id = WorldObjectId(1)
            aggregate.add_object(WorldObject(obj_id, Coordinate(0, 0, 0), ObjectTypeEnum.SIGN))
            aggregate.clear_events()
            
            # When
            aggregate.move_object(obj_id, Coordinate(1, 1, 0), WorldTick(10))
            
            # Then
            events = aggregate.get_events()
            assert any(isinstance(e, AreaEnteredEvent) for e in events)
            assert any(isinstance(e, AreaTriggeredEvent) and e.trigger_type == TriggerTypeEnum.WARP for e in events)

        def test_area_exit_event(self, aggregate):
            # Given
            warp = WarpTrigger(SpotId(2), Coordinate(0, 0, 0))
            area_trigger = AreaTrigger(AreaTriggerId(1), RectArea(0, 0, 0, 0, 0, 0), warp)
            aggregate.add_area_trigger(area_trigger)
            
            obj_id = WorldObjectId(1)
            aggregate.add_object(WorldObject(obj_id, Coordinate(0, 0, 0), ObjectTypeEnum.SIGN))
            aggregate.clear_events()
            
            # When
            aggregate.move_object(obj_id, Coordinate(1, 1, 0), WorldTick(10))
            
            # Then
            events = aggregate.get_events()
            assert any(isinstance(e, AreaExitedEvent) for e in events)

        def test_check_and_activate_trigger_manual(self, aggregate):
            # Given
            warp = WarpTrigger(SpotId(2), Coordinate(0, 0, 0))
            aggregate.add_area_trigger(AreaTrigger(AreaTriggerId(1), RectArea(1, 1, 1, 1, 0, 0), warp))
            
            # When
            trigger = aggregate.check_and_activate_trigger(Coordinate(1, 1, 0))
            
            # Then
            assert trigger == warp

    class TestExceptions:
        def test_move_actor_not_an_actor_raises_error(self, aggregate):
            obj_id = WorldObjectId(1)
            aggregate.add_object(WorldObject(obj_id, Coordinate(0, 0, 0), ObjectTypeEnum.CHEST))
            with pytest.raises(NotAnActorException):
                aggregate.move_actor(obj_id, DirectionEnum.NORTH, WorldTick(10))

        def test_add_duplicate_area_trigger_raises_error(self, aggregate):
            trigger = AreaTrigger(AreaTriggerId(1), PointArea(Coordinate(0, 0, 0)), DamageTrigger(10))
            aggregate.add_area_trigger(trigger)
            with pytest.raises(DuplicateAreaTriggerException):
                aggregate.add_area_trigger(trigger)

        def test_remove_non_existent_area_trigger_raises_error(self, aggregate):
            with pytest.raises(AreaTriggerNotFoundException):
                aggregate.remove_area_trigger(AreaTriggerId(999))

        def test_get_direction_to_same_coordinate_raises_error(self, aggregate):
            coord = Coordinate(0, 0, 0)
            with pytest.raises(SameCoordinateDirectionException):
                coord.direction_to(coord)

        def test_get_actor_success(self, aggregate):
            # Given
            obj_id = WorldObjectId(1)
            actor = ActorComponent()
            aggregate.add_object(WorldObject(obj_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER, component=actor))
            
            # When
            obj = aggregate.get_actor(obj_id)
            
            # Then
            assert obj.object_id == obj_id
            assert obj.is_actor is True

        def test_get_actor_raises_error_for_non_actor(self, aggregate):
            # Given
            obj_id = WorldObjectId(1)
            aggregate.add_object(WorldObject(obj_id, Coordinate(0, 0, 0), ObjectTypeEnum.CHEST))
            
            # When & Then
            with pytest.raises(NotAnActorException):
                aggregate.get_actor(obj_id)

    class TestBugFixes:
        def test_move_object_from_wall_stays_impassable(self, spot_id):
            # Given: A road and a wall
            tiles = [
                Tile(Coordinate(0, 0, 0), TerrainType.road()),
                Tile(Coordinate(1, 1, 0), TerrainType.wall())
            ]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            
            # Add a ghost actor on the wall
            ghost_cap = MovementCapability.ghost()
            actor_comp = ActorComponent(capability=ghost_cap)
            obj_id = WorldObjectId(1)
            obj = WorldObject(obj_id, Coordinate(1, 1, 0), ObjectTypeEnum.PLAYER, is_blocking=True, component=actor_comp)
            aggregate.add_object(obj)
            
            # The wall is now blocked by the object (override is False)
            assert aggregate.is_walkable(Coordinate(1, 1, 0)) is False
            
            # When: Move the object away from the wall
            aggregate.move_object(obj_id, Coordinate(0, 0, 0), WorldTick(10), ghost_cap)
            
            # Then: The wall should still be impassable because it's a wall (reset override to None)
            assert aggregate.is_walkable(Coordinate(1, 1, 0)) is False
            # Check the actual tile override
            assert aggregate.get_tile(Coordinate(1, 1, 0))._is_walkable_override is None

    class TestVisibilityImprovement:
        def test_visibility_through_missing_tiles(self, spot_id):
            # Given: Two tiles at (0,0,0) and (2,2,0), but nothing at (1,1,0)
            tiles = [
                Tile(Coordinate(0, 0, 0), TerrainType.road()),
                Tile(Coordinate(2, 2, 0), TerrainType.road())
            ]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            
            # When & Then: Should be visible because (1,1,0) is missing (transparent)
            assert aggregate.is_visible(Coordinate(0, 0, 0), Coordinate(2, 2, 0)) is True

    class TestInteraction:
        def test_perform_action_sets_busy(self, aggregate):
            # Given
            obj_id = WorldObjectId(1)
            obj = WorldObject(obj_id, Coordinate(0, 0), ObjectTypeEnum.PLAYER)
            aggregate.add_object(obj)
            current_tick = WorldTick(10)
            
            # When
            aggregate.perform_action(obj_id, 5, current_tick)
            
            # Then
            assert obj.is_busy(current_tick) is True
            assert obj.busy_until == WorldTick(15)

        def test_perform_action_fails_when_busy(self, aggregate):
            # Given
            obj_id = WorldObjectId(1)
            obj = WorldObject(obj_id, Coordinate(0, 0), ObjectTypeEnum.PLAYER, busy_until=WorldTick(20))
            aggregate._add_object_to_internal_storage(obj)
            
            # When & Then
            with pytest.raises(ActorBusyException):
                aggregate.perform_action(obj_id, 5, WorldTick(15))

        def test_interact_success_adjacent(self, aggregate):
            # Given
            actor_id = WorldObjectId(1)
            target_id = WorldObjectId(2)
            actor = WorldObject(actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER, 
                                component=ActorComponent(direction=DirectionEnum.SOUTH))
            target = WorldObject(target_id, Coordinate(0, 1, 0), ObjectTypeEnum.NPC, 
                                 component=InteractableComponent("talk", {"name": "Bob"}))
            aggregate.add_object(actor)
            aggregate.add_object(target)
            aggregate.clear_events()
            current_tick = WorldTick(10)

            # When
            aggregate.interact_with(actor_id, target_id, current_tick)

            # Then
            events = aggregate.get_events()
            assert any(isinstance(e, WorldObjectInteractedEvent) for e in events)
            event = [e for e in events if isinstance(e, WorldObjectInteractedEvent)][0]
            assert event.actor_id == actor_id
            assert event.target_id == target_id
            assert event.interaction_type == InteractionTypeEnum.TALK
            assert event.data == {"name": "Bob"}
            
            # アクターがビジー状態になっていること
            assert actor.is_busy(current_tick) is True
            assert actor.busy_until == current_tick.add_duration(1) # デフォルト1

        def test_interact_fails_when_busy(self, aggregate):
            # Given
            actor_id = WorldObjectId(1)
            target_id = WorldObjectId(2)
            actor = WorldObject(actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER, 
                                component=ActorComponent(direction=DirectionEnum.SOUTH),
                                busy_until=WorldTick(20))
            target = WorldObject(target_id, Coordinate(0, 1, 0), ObjectTypeEnum.NPC, 
                                 component=InteractableComponent("talk"))
            aggregate.add_object(actor)
            aggregate.add_object(target)
            
            # When & Then
            with pytest.raises(ActorBusyException):
                aggregate.interact_with(actor_id, target_id, WorldTick(15))

        def test_interact_fails_too_far(self, aggregate):
            # Given
            actor_id = WorldObjectId(1)
            target_id = WorldObjectId(2)
            actor = WorldObject(actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER, 
                                component=ActorComponent(direction=DirectionEnum.SOUTH))
            target = WorldObject(target_id, Coordinate(2, 2, 0), ObjectTypeEnum.NPC, 
                                 component=InteractableComponent("talk"))
            aggregate.add_object(actor)
            aggregate.add_object(target)

            # When & Then
            with pytest.raises(InteractionOutOfRangeException):
                aggregate.interact_with(actor_id, target_id, WorldTick(10))

        def test_interact_fails_wrong_direction(self, aggregate):
            # Given
            actor_id = WorldObjectId(1)
            target_id = WorldObjectId(2)
            # Actor is at (0,0), Target is at (0,1) (South). Actor faces North.
            actor = WorldObject(actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER, 
                                component=ActorComponent(direction=DirectionEnum.NORTH))
            target = WorldObject(target_id, Coordinate(0, 1, 0), ObjectTypeEnum.NPC, 
                                 component=InteractableComponent("talk"))
            aggregate.add_object(actor)
            aggregate.add_object(target)

            # When & Then
            with pytest.raises(NotFacingTargetException):
                aggregate.interact_with(actor_id, target_id, WorldTick(10))

        def test_interact_fails_not_interactable(self, aggregate):
            # Given
            actor_id = WorldObjectId(1)
            target_id = WorldObjectId(2)
            actor = WorldObject(actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER, 
                                component=ActorComponent(direction=DirectionEnum.SOUTH))
            target = WorldObject(target_id, Coordinate(0, 1, 0), ObjectTypeEnum.CHEST) # No component
            aggregate.add_object(actor)
            aggregate.add_object(target)

            # When & Then
            with pytest.raises(NotInteractableException):
                aggregate.interact_with(actor_id, target_id, WorldTick(10))

    class TestWeatherEffects:
        def test_weather_affects_vision_range(self, spot_id):
            # Given: 霧 (FOG, intensity 1.0) -> Vision reduction = 8.
            tiles = [Tile(Coordinate(x, 0), TerrainType.road()) for x in range(11)]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            aggregate.set_weather(WeatherState(WeatherTypeEnum.FOG, 1.0))
            
            obj1 = WorldObject(WorldObjectId(1), Coordinate(0, 0), ObjectTypeEnum.CHEST)
            obj2 = WorldObject(WorldObjectId(2), Coordinate(5, 0), ObjectTypeEnum.CHEST)
            obj3 = WorldObject(WorldObjectId(3), Coordinate(10, 0), ObjectTypeEnum.CHEST)
            aggregate.add_object(obj1)
            aggregate.add_object(obj2)
            aggregate.add_object(obj3)

            # When
            # Default vision distance is usually large. Let's assume 10.
            # 10 - 8 = 2.
            in_range = aggregate.get_objects_in_range(Coordinate(0, 0), 10)
            
            # Then
            assert obj1 in in_range
            assert obj2 not in in_range
            assert obj3 not in in_range

        def test_weather_affects_movement_cost(self, spot_id):
            # Given: 嵐 (STORM, intensity 1.0) -> Multiplier = 1.8.
            tiles = [Tile(Coordinate(0, 0), TerrainType.road()), Tile(Coordinate(1, 0), TerrainType.road())]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            aggregate.set_weather(WeatherState(WeatherTypeEnum.STORM, 1.0))
            
            # Road base cost is 1.0. 1.0 * 1.8 = 1.8.
            cost = aggregate.get_movement_cost(Coordinate(1, 0), MovementCapability.normal_walk())
            assert cost == 1.8

        def test_indoor_ignores_weather(self, spot_id):
            # Given: 屋内 (INDOOR)
            tiles = [
                Tile(Coordinate(0, 0), TerrainType.road()),
                Tile(Coordinate(10, 0), TerrainType.road())
            ]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles, environment_type=EnvironmentTypeEnum.INDOOR)
            
            # 天候を設定しようとしても Clear になるはず
            aggregate.set_weather(WeatherState(WeatherTypeEnum.BLIZZARD, 1.0))
            assert aggregate.weather_state.weather_type == WeatherTypeEnum.CLEAR
            
            # 視界も制限されない
            # CLEAR -> Reduction 0.
            # get_objects_in_range(..., 10) should see things at dist 10.
            obj = WorldObject(WorldObjectId(2), Coordinate(10, 0), ObjectTypeEnum.CHEST)
            aggregate.add_object(obj)
            
            in_range = aggregate.get_objects_in_range(Coordinate(0, 0), 10)
            assert obj in in_range

    class TestGetObjectsInRangeBulk:
        """get_objects_in_range_bulk の正常・境界・例外ケース"""

        def test_bulk_returns_same_as_individual_calls(self, spot_id):
            # Given: 複数オブジェクトを配置
            tiles = [Tile(Coordinate(x, y), TerrainType.road()) for x in range(5) for y in range(5)]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            obj1 = WorldObject(WorldObjectId(1), Coordinate(1, 1), ObjectTypeEnum.CHEST)
            obj2 = WorldObject(WorldObjectId(2), Coordinate(2, 2), ObjectTypeEnum.CHEST)
            obj3 = WorldObject(WorldObjectId(3), Coordinate(4, 4), ObjectTypeEnum.CHEST)
            aggregate.add_object(obj1)
            aggregate.add_object(obj2)
            aggregate.add_object(obj3)

            centers_with_range = [
                (Coordinate(2, 2), 2),
                (Coordinate(0, 0), 1),
                (Coordinate(4, 4), 0),
            ]

            # When
            bulk_result = aggregate.get_objects_in_range_bulk(centers_with_range)

            # Then: 各クエリは単体の get_objects_in_range と一致
            assert len(bulk_result) == 3
            single_0 = aggregate.get_objects_in_range(Coordinate(2, 2), 2)
            single_1 = aggregate.get_objects_in_range(Coordinate(0, 0), 1)
            single_2 = aggregate.get_objects_in_range(Coordinate(4, 4), 0)
            assert set(bulk_result[0]) == set(single_0)
            assert set(bulk_result[1]) == set(single_1)
            assert set(bulk_result[2]) == set(single_2)
            assert len(bulk_result[0]) == 2
            assert obj1 in bulk_result[0]
            assert obj2 in bulk_result[0]
            assert obj3 not in bulk_result[0]
            assert len(bulk_result[2]) == 1
            assert obj3 in bulk_result[2]

        def test_bulk_empty_input_returns_empty_list(self, aggregate):
            # When
            result = aggregate.get_objects_in_range_bulk([])

            # Then
            assert result == []

        def test_bulk_single_query(self, spot_id):
            # Given
            tiles = [Tile(Coordinate(0, 0), TerrainType.road()), Tile(Coordinate(1, 0), TerrainType.road())]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            obj = WorldObject(WorldObjectId(1), Coordinate(1, 0), ObjectTypeEnum.CHEST)
            aggregate.add_object(obj)

            # When
            result = aggregate.get_objects_in_range_bulk([(Coordinate(0, 0), 2)])

            # Then
            assert len(result) == 1
            assert len(result[0]) == 1
            assert obj in result[0]

        def test_bulk_multiple_centers_same_map(self, spot_id):
            # Given: 3つの中心で一括取得
            tiles = [Tile(Coordinate(x, y), TerrainType.road()) for x in range(5) for y in range(5)]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            for i, (x, y) in enumerate([(0, 0), (2, 2), (4, 4)]):
                aggregate.add_object(WorldObject(WorldObjectId(i + 1), Coordinate(x, y), ObjectTypeEnum.CHEST))

            centers_with_range = [
                (Coordinate(0, 0), 0),
                (Coordinate(2, 2), 1),
                (Coordinate(4, 4), 10),
            ]

            # When
            result = aggregate.get_objects_in_range_bulk(centers_with_range)

            # Then
            assert len(result) == 3
            assert len(result[0]) == 1
            assert result[0][0].object_id == WorldObjectId(1)
            assert len(result[1]) == 1
            assert result[1][0].object_id == WorldObjectId(2)
            assert len(result[2]) == 3

        def test_bulk_weather_affects_all_queries(self, spot_id):
            # Given: 霧で視界減衰
            tiles = [Tile(Coordinate(x, 0), TerrainType.road()) for x in range(11)]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            aggregate.set_weather(WeatherState(WeatherTypeEnum.FOG, 1.0))
            obj_near = WorldObject(WorldObjectId(1), Coordinate(0, 0), ObjectTypeEnum.CHEST)
            obj_far = WorldObject(WorldObjectId(2), Coordinate(10, 0), ObjectTypeEnum.CHEST)
            aggregate.add_object(obj_near)
            aggregate.add_object(obj_far)

            centers_with_range = [
                (Coordinate(0, 0), 10),
                (Coordinate(10, 0), 10),
            ]

            # When
            result = aggregate.get_objects_in_range_bulk(centers_with_range)

            # Then: 両方のクエリとも天候が適用され、遠くは見えない
            assert len(result) == 2
            assert obj_near in result[0]
            assert obj_far not in result[0]
            assert obj_far in result[1]
            assert obj_near not in result[1]

        def test_bulk_order_of_results_matches_input_order(self, spot_id):
            # Given
            tiles = [Tile(Coordinate(x, y), TerrainType.road()) for x in range(3) for y in range(3)]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            aggregate.add_object(WorldObject(WorldObjectId(1), Coordinate(1, 1), ObjectTypeEnum.CHEST))

            centers_with_range = [
                (Coordinate(1, 1), 0),
                (Coordinate(0, 0), 5),
                (Coordinate(2, 2), 5),
            ]

            # When
            result = aggregate.get_objects_in_range_bulk(centers_with_range)

            # Then: 返り値の順序が入力の (center, range) 順と一致
            assert len(result) == 3
            assert result[0][0].object_id == WorldObjectId(1)
            assert len(result[1]) == 1
            assert len(result[2]) == 1

    class TestIsVisibleBatch:
        """is_visible_batch の正常・境界・例外ケース"""

        def test_batch_returns_same_as_individual_calls(self, aggregate):
            # Given: 障害物なしのマップ
            pairs = [
                (Coordinate(0, 0), Coordinate(2, 2)),
                (Coordinate(0, 0), Coordinate(1, 1)),
                (Coordinate(2, 2), Coordinate(0, 0)),
            ]

            # When
            batch_result = aggregate.is_visible_batch(pairs)

            # Then: 各ペアは単体の is_visible と一致
            assert len(batch_result) == 3
            assert batch_result[0] is aggregate.is_visible(Coordinate(0, 0), Coordinate(2, 2))
            assert batch_result[1] is aggregate.is_visible(Coordinate(0, 0), Coordinate(1, 1))
            assert batch_result[2] is aggregate.is_visible(Coordinate(2, 2), Coordinate(0, 0))
            assert batch_result[0] is True
            assert batch_result[1] is True
            assert batch_result[2] is True

        def test_batch_empty_input_returns_empty_list(self, aggregate):
            # When
            result = aggregate.is_visible_batch([])

            # Then
            assert result == []

        def test_batch_deduplicates_same_pair(self, spot_id):
            # Given: 同一ペアを複数回含む
            tiles = [
                Tile(Coordinate(0, 0), TerrainType.road()),
                Tile(Coordinate(1, 1), TerrainType.wall()),
                Tile(Coordinate(2, 2), TerrainType.road()),
            ]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            pairs = [
                (Coordinate(0, 0), Coordinate(2, 2)),
                (Coordinate(0, 0), Coordinate(2, 2)),
                (Coordinate(2, 2), Coordinate(0, 0)),
            ]

            # When
            result = aggregate.is_visible_batch(pairs)

            # Then: 順序は入力順、同一ペアは同じ結果（壁で遮られて False）
            assert len(result) == 3
            assert result[0] is False
            assert result[1] is False
            assert result[2] is False
            assert result[0] == result[1]

        def test_batch_out_of_bounds_returns_false(self, aggregate):
            # Given: マップ外の座標を含むペア
            pairs = [
                (Coordinate(0, 0), Coordinate(99, 99, 0)),
                (Coordinate(99, 99, 0), Coordinate(0, 0)),
            ]

            # When
            result = aggregate.is_visible_batch(pairs)

            # Then
            assert len(result) == 2
            assert result[0] is False
            assert result[1] is False

        def test_batch_blocked_pairs_return_false(self, spot_id):
            # Given: 壁で遮られたペア
            tiles = [
                Tile(Coordinate(0, 0), TerrainType.road()),
                Tile(Coordinate(1, 1), TerrainType.wall()),
                Tile(Coordinate(2, 2), TerrainType.road()),
            ]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            pairs = [(Coordinate(0, 0), Coordinate(2, 2))]

            # When
            result = aggregate.is_visible_batch(pairs)

            # Then
            assert len(result) == 1
            assert result[0] is False

        def test_batch_visible_pairs_return_true(self, aggregate):
            # Given: 障害物なし
            pairs = [
                (Coordinate(0, 0), Coordinate(2, 2)),
                (Coordinate(0, 0), Coordinate(0, 0)),
            ]

            # When
            result = aggregate.is_visible_batch(pairs)

            # Then
            assert len(result) == 2
            assert result[0] is True
            assert result[1] is True

        def test_batch_order_of_results_matches_input_order(self, spot_id):
            # Given: 可視と不可視が混在（中間タイルで遮られるペアを含む）
            tiles = [
                Tile(Coordinate(0, 0), TerrainType.road()),
                Tile(Coordinate(1, 1), TerrainType.wall()),
                Tile(Coordinate(2, 2), TerrainType.road()),
            ]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            # (0,0)-(1,1): 見える, (0,0)-(2,2): (1,1)で遮られて不可視, (2,2)-(0,0): (1,1)で遮られて不可視
            pairs = [
                (Coordinate(0, 0), Coordinate(1, 1)),
                (Coordinate(0, 0), Coordinate(2, 2)),
                (Coordinate(2, 2), Coordinate(0, 0)),
            ]

            # When
            result = aggregate.is_visible_batch(pairs)

            # Then: 入力順で [True, False, False]
            assert len(result) == 3
            assert result[0] is True
            assert result[1] is False
            assert result[2] is False

        def test_batch_same_coordinate_returns_true(self, aggregate):
            # Given: 同一座標ペア
            pairs = [(Coordinate(1, 1), Coordinate(1, 1))]

            # When
            result = aggregate.is_visible_batch(pairs)

            # Then
            assert len(result) == 1
            assert result[0] is True

    class TestGetActorsInPack:
        """get_actors_in_pack の正常・境界・例外ケース"""

        def test_returns_only_autonomous_actors_in_pack(self, spot_id):
            # Given: 同一 pack の自律アクター2体と、別 pack の1体、pack なしの1体、非アクター1体
            tiles = [Tile(Coordinate(x, y), TerrainType.road()) for x in range(3) for y in range(3)]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            pack_a = PackId.create("pack_a")
            pack_b = PackId.create("pack_b")

            actor1 = WorldObject(
                WorldObjectId(1), Coordinate(0, 0), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(pack_id=pack_a),
            )
            actor2 = WorldObject(
                WorldObjectId(2), Coordinate(1, 0), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(pack_id=pack_a),
            )
            actor3 = WorldObject(
                WorldObjectId(3), Coordinate(2, 0), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(pack_id=pack_b),
            )
            actor4 = WorldObject(
                WorldObjectId(4), Coordinate(0, 1), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(pack_id=None),
            )
            chest = WorldObject(WorldObjectId(5), Coordinate(1, 1), ObjectTypeEnum.CHEST)
            aggregate.add_object(actor1)
            aggregate.add_object(actor2)
            aggregate.add_object(actor3)
            aggregate.add_object(actor4)
            aggregate.add_object(chest)

            # When
            in_pack_a = aggregate.get_actors_in_pack(pack_a)
            in_pack_b = aggregate.get_actors_in_pack(pack_b)

            # Then
            assert len(in_pack_a) == 2
            assert {obj.object_id for obj in in_pack_a} == {WorldObjectId(1), WorldObjectId(2)}
            assert len(in_pack_b) == 1
            assert in_pack_b[0].object_id == WorldObjectId(3)

        def test_returns_empty_when_no_actor_in_pack(self, spot_id):
            # Given: pack に属するアクターがいない
            tiles = [Tile(Coordinate(0, 0), TerrainType.road())]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            pack_a = PackId.create("pack_a")
            actor = WorldObject(
                WorldObjectId(1), Coordinate(0, 0), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(pack_id=None),
            )
            aggregate.add_object(actor)

            # When
            result = aggregate.get_actors_in_pack(pack_a)

            # Then
            assert result == []

        def test_returns_empty_when_map_has_no_actors(self, aggregate):
            # Given: アクターが1体もいないマップ
            pack_id = PackId.create("any_pack")

            # When
            result = aggregate.get_actors_in_pack(pack_id)

            # Then
            assert result == []

        def test_players_and_non_autonomous_actors_excluded(self, spot_id):
            # Given: プレイヤー（ActorComponent）と自律アクター（AutonomousBehaviorComponent）
            tiles = [Tile(Coordinate(x, y), TerrainType.road()) for x in range(2) for y in range(2)]
            aggregate = PhysicalMapAggregate.create(spot_id, tiles)
            pack_id = PackId.create("pack")
            player = WorldObject(
                WorldObjectId(1), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=None),
            )
            monster = WorldObject(
                WorldObjectId(2), Coordinate(1, 0), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(pack_id=pack_id),
            )
            aggregate.add_object(player)
            aggregate.add_object(monster)

            # When
            result = aggregate.get_actors_in_pack(pack_id)

            # Then: 自律アクターのみ
            assert len(result) == 1
            assert result[0].object_id == WorldObjectId(2)

    class TestChestAndDoor:
        """チェスト・ドアのインタラクションと収納・取得のテスト"""

        def test_interact_with_open_chest_toggles_state(self, aggregate):
            actor_id = WorldObjectId(1)
            chest_id = WorldObjectId(2)
            actor = WorldObject(
                actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH),
            )
            chest = WorldObject(
                chest_id, Coordinate(0, 1, 0), ObjectTypeEnum.CHEST,
                component=ChestComponent(is_open=False),
            )
            aggregate.add_object(actor)
            aggregate.add_object(chest)
            aggregate.clear_events()
            current_tick = WorldTick(10)
            assert chest.component.is_open is False

            aggregate.interact_with(actor_id, chest_id, current_tick)

            assert chest.component.is_open is True
            events = aggregate.get_events()
            assert any(isinstance(e, WorldObjectInteractedEvent) for e in events)
            event = next(e for e in events if isinstance(e, WorldObjectInteractedEvent))
            assert event.interaction_type == InteractionTypeEnum.OPEN_CHEST

        def test_interact_with_open_door_toggles_state_and_blocking(self, aggregate):
            actor_id = WorldObjectId(1)
            door_id = WorldObjectId(2)
            actor = WorldObject(
                actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH),
            )
            door = WorldObject(
                door_id, Coordinate(0, 1, 0), ObjectTypeEnum.DOOR,
                component=DoorComponent(is_open=False, is_locked=False),
            )
            aggregate.add_object(actor)
            aggregate.add_object(door)
            aggregate.clear_events()
            current_tick = WorldTick(10)
            assert door.component.is_open is False
            assert door.is_blocking is True

            aggregate.interact_with(actor_id, door_id, current_tick)

            assert door.component.is_open is True
            assert door.is_blocking is False
            events = aggregate.get_events()
            assert any(isinstance(e, WorldObjectBlockingChangedEvent) for e in events)

        def test_interact_with_locked_door_raises(self, aggregate):
            actor_id = WorldObjectId(1)
            door_id = WorldObjectId(2)
            actor = WorldObject(
                actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH),
            )
            door = WorldObject(
                door_id, Coordinate(0, 1, 0), ObjectTypeEnum.DOOR,
                component=DoorComponent(is_locked=True),
            )
            aggregate.add_object(actor)
            aggregate.add_object(door)

            with pytest.raises(LockedDoorException):
                aggregate.interact_with(actor_id, door_id, WorldTick(10))

        def test_interact_with_locked_door_emits_no_event_and_actor_not_busy(self, aggregate):
            """apply_interaction_from が例外を投げた場合、イベント発行・ビジー設定は行わないこと"""
            actor_id = WorldObjectId(1)
            door_id = WorldObjectId(2)
            actor = WorldObject(
                actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH),
            )
            door = WorldObject(
                door_id, Coordinate(0, 1, 0), ObjectTypeEnum.DOOR,
                component=DoorComponent(is_locked=True),
            )
            aggregate.add_object(actor)
            aggregate.add_object(door)
            aggregate.clear_events()
            events_before = len(aggregate.get_events())
            assert actor.is_busy(WorldTick(10)) is False

            with pytest.raises(LockedDoorException):
                aggregate.interact_with(actor_id, door_id, WorldTick(10))

            events_after = aggregate.get_events()
            assert len(events_after) == events_before
            assert not any(isinstance(e, WorldObjectInteractedEvent) for e in events_after)
            assert actor.is_busy(WorldTick(10)) is False

        def test_store_item_in_chest_success(self, aggregate, spot_id):
            actor_id = WorldObjectId(1)
            chest_id = WorldObjectId(2)
            actor = WorldObject(
                actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH),
            )
            chest = WorldObject(
                chest_id, Coordinate(0, 1, 0), ObjectTypeEnum.CHEST,
                component=ChestComponent(is_open=True),
            )
            aggregate.add_object(actor)
            aggregate.add_object(chest)
            aggregate.clear_events()
            item_id = ItemInstanceId.create(100)
            player_id_value = 999

            aggregate.store_item_in_chest(actor_id, chest_id, item_id, player_id_value)

            assert chest.component.has_item(item_id) is True
            events = aggregate.get_events()
            stored = next(e for e in events if isinstance(e, ItemStoredInChestEvent))
            assert stored.chest_id == chest_id
            assert stored.actor_id == actor_id
            assert stored.item_instance_id == item_id
            assert stored.player_id_value == player_id_value

        def test_store_item_in_chest_raises_when_closed(self, aggregate):
            actor_id = WorldObjectId(1)
            chest_id = WorldObjectId(2)
            actor = WorldObject(
                actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH),
            )
            chest = WorldObject(
                chest_id, Coordinate(0, 1, 0), ObjectTypeEnum.CHEST,
                component=ChestComponent(is_open=False),
            )
            aggregate.add_object(actor)
            aggregate.add_object(chest)
            item_id = ItemInstanceId.create(100)

            with pytest.raises(ChestClosedException):
                aggregate.store_item_in_chest(actor_id, chest_id, item_id, 1)

        def test_store_item_in_chest_raises_when_not_chest(self, aggregate):
            actor_id = WorldObjectId(1)
            target_id = WorldObjectId(2)
            actor = WorldObject(
                actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH),
            )
            target = WorldObject(
                target_id, Coordinate(0, 1, 0), ObjectTypeEnum.NPC,
                component=InteractableComponent("talk"),
            )
            aggregate.add_object(actor)
            aggregate.add_object(target)
            item_id = ItemInstanceId.create(100)

            with pytest.raises(NotAChestException):
                aggregate.store_item_in_chest(actor_id, target_id, item_id, 1)

        def test_store_item_in_chest_raises_when_too_far(self, aggregate):
            actor_id = WorldObjectId(1)
            chest_id = WorldObjectId(2)
            actor = WorldObject(
                actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH),
            )
            chest = WorldObject(
                chest_id, Coordinate(2, 0, 0), ObjectTypeEnum.CHEST,
                component=ChestComponent(is_open=True),
            )
            aggregate.add_object(actor)
            aggregate.add_object(chest)
            item_id = ItemInstanceId.create(100)

            with pytest.raises(InteractionOutOfRangeException):
                aggregate.store_item_in_chest(actor_id, chest_id, item_id, 1)

        def test_take_item_from_chest_success(self, aggregate):
            actor_id = WorldObjectId(1)
            chest_id = WorldObjectId(2)
            item_id = ItemInstanceId.create(50)
            actor = WorldObject(
                actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH),
            )
            chest = WorldObject(
                chest_id, Coordinate(0, 1, 0), ObjectTypeEnum.CHEST,
                component=ChestComponent(is_open=True, item_ids=[item_id]),
            )
            aggregate.add_object(actor)
            aggregate.add_object(chest)
            aggregate.clear_events()
            player_id_value = 1

            aggregate.take_item_from_chest(actor_id, chest_id, item_id, player_id_value)

            assert chest.component.has_item(item_id) is False
            events = aggregate.get_events()
            taken = next(e for e in events if isinstance(e, ItemTakenFromChestEvent))
            assert taken.chest_id == chest_id
            assert taken.item_instance_id == item_id
            assert taken.player_id_value == player_id_value

        def test_take_item_from_chest_raises_when_item_not_in_chest(self, aggregate):
            actor_id = WorldObjectId(1)
            chest_id = WorldObjectId(2)
            actor = WorldObject(
                actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH),
            )
            chest = WorldObject(
                chest_id, Coordinate(0, 1, 0), ObjectTypeEnum.CHEST,
                component=ChestComponent(is_open=True),
            )
            aggregate.add_object(actor)
            aggregate.add_object(chest)
            item_id = ItemInstanceId.create(999)

            with pytest.raises(ItemNotInChestException):
                aggregate.take_item_from_chest(actor_id, chest_id, item_id, 1)

        def test_take_item_from_chest_raises_when_closed(self, aggregate):
            actor_id = WorldObjectId(1)
            chest_id = WorldObjectId(2)
            item_id = ItemInstanceId.create(50)
            actor = WorldObject(
                actor_id, Coordinate(0, 0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(direction=DirectionEnum.SOUTH),
            )
            chest = WorldObject(
                chest_id, Coordinate(0, 1, 0), ObjectTypeEnum.CHEST,
                component=ChestComponent(is_open=False, item_ids=[item_id]),
            )
            aggregate.add_object(actor)
            aggregate.add_object(chest)

            with pytest.raises(ChestClosedException):
                aggregate.take_item_from_chest(actor_id, chest_id, item_id, 1)
