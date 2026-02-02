import pytest
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, TerrainTypeEnum, TriggerTypeEnum, DirectionEnum, MovementCapabilityEnum
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
    SameCoordinateDirectionException
)
from ai_rpg_world.domain.world.value_object.area_trigger_id import AreaTriggerId
from ai_rpg_world.domain.world.value_object.area import PointArea, RectArea
from ai_rpg_world.domain.world.entity.area_trigger import AreaTrigger
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent, InteractableComponent
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
    WorldObjectInteractedEvent
)
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
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
            assert event.interaction_type == "talk"
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
