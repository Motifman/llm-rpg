"""PhysicalMapAggregate の get_objects_at / validate_placement / 踏んだら発火トリガー のテスト"""

import pytest
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import (
    ActorComponent,
    PlaceableComponent,
    StaticPlaceableInnerComponent,
    GroundItemComponent,
)
from ai_rpg_world.domain.world.entity.map_trigger import DamageTrigger
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, DirectionEnum
from ai_rpg_world.domain.world.event.map_events import ObjectTriggeredEvent, WorldObjectAddedEvent
from ai_rpg_world.domain.world.exception.map_exception import InvalidPlacementException, DuplicateObjectException
from ai_rpg_world.domain.world.value_object.movement_capability import MovementCapability
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
from ai_rpg_world.domain.common.value_object import WorldTick


@pytest.fixture
def spot_id():
    return SpotId(1)


@pytest.fixture
def tiles_5x5():
    return [Tile(Coordinate(x, y), TerrainType.road()) for x in range(5) for y in range(5)]


@pytest.fixture
def aggregate(spot_id, tiles_5x5):
    return PhysicalMapAggregate.create(spot_id, tiles_5x5)


class TestGetObjectsAt:
    def test_empty_coordinate_returns_empty_list(self, aggregate):
        objs = aggregate.get_objects_at(Coordinate(2, 2))
        assert objs == []

    def test_returns_objects_at_coordinate(self, aggregate):
        c = Coordinate(2, 2)
        o1 = WorldObject(WorldObjectId(1), c, ObjectTypeEnum.GROUND_ITEM, is_blocking=False, component=GroundItemComponent(ItemInstanceId(100)))
        o2 = WorldObject(WorldObjectId(2), c, ObjectTypeEnum.GROUND_ITEM, is_blocking=False, component=GroundItemComponent(ItemInstanceId(101)))
        aggregate.add_object(o1)
        aggregate.add_object(o2)
        objs = aggregate.get_objects_at(c)
        assert len(objs) == 2
        ids = {obj.object_id for obj in objs}
        assert WorldObjectId(1) in ids
        assert WorldObjectId(2) in ids


class TestValidatePlacement:
    def test_valid_empty_tile_passes(self, aggregate):
        aggregate.validate_placement(Coordinate(2, 2), is_blocking=True)

    def test_invalid_out_of_bounds_raises(self, aggregate):
        with pytest.raises(InvalidPlacementException):
            aggregate.validate_placement(Coordinate(10, 10), is_blocking=True)

    def test_blocking_on_existing_blocking_raises(self, aggregate):
        c = Coordinate(2, 2)
        aggregate.add_object(WorldObject(WorldObjectId(1), c, ObjectTypeEnum.CHEST, is_blocking=True))
        with pytest.raises(DuplicateObjectException):
            aggregate.validate_placement(c, is_blocking=True)


class TestObjectTriggerOnStep:
    def test_move_onto_tile_with_trigger_fires_object_triggered_event(self, aggregate):
        trap_id = WorldObjectId(100)
        trap_component = PlaceableComponent(
            item_spec_id=ItemSpecId(1),
            inner=StaticPlaceableInnerComponent(),
            trigger_on_step=DamageTrigger(10),
        )
        trap = WorldObject(
            object_id=trap_id,
            coordinate=Coordinate(2, 2),
            object_type=ObjectTypeEnum.SWITCH,
            is_blocking=False,
            component=trap_component,
        )
        aggregate.add_object(trap)

        actor_id = WorldObjectId(1)
        actor = WorldObject(
            object_id=actor_id,
            coordinate=Coordinate(2, 1),
            object_type=ObjectTypeEnum.PLAYER,
            is_blocking=False,
            component=ActorComponent(capability=MovementCapability.normal_walk()),
        )
        aggregate.add_object(actor)
        aggregate.clear_events()

        aggregate.move_object(actor_id, Coordinate(2, 2), WorldTick(0))

        triggered = [e for e in aggregate.get_events() if isinstance(e, ObjectTriggeredEvent)]
        assert len(triggered) == 1
        assert triggered[0].object_id == trap_id
        assert triggered[0].actor_id == actor_id


class TestGroundItemMultipleAtSameCoordinate:
    """GROUND_ITEM は当たり判定なしのため同一座標に複数配置可能"""

    def test_multiple_ground_items_at_same_coordinate(self, aggregate):
        c = Coordinate(2, 2)
        for i in range(3):
            obj = WorldObject(
                object_id=WorldObjectId(100 + i),
                coordinate=c,
                object_type=ObjectTypeEnum.GROUND_ITEM,
                is_blocking=False,
                component=GroundItemComponent(ItemInstanceId(200 + i)),
            )
            aggregate.add_object(obj)
        objs = aggregate.get_objects_at(c)
        assert len(objs) == 3
        assert aggregate.is_passable(c, MovementCapability.normal_walk())
