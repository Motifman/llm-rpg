import pytest
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import HarvestableComponent, ActorComponent
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, DirectionEnum
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.event.harvest_events import (
    HarvestStartedEvent,
    HarvestCancelledEvent,
    HarvestCompletedEvent
)
from ai_rpg_world.domain.world.exception.harvest_exception import (
    NotHarvestableException,
    ResourceExhaustedException,
    HarvestInProgressException,
    HarvestNotStartedException
)
from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId
from ai_rpg_world.domain.world.exception.map_exception import (
    InteractionOutOfRangeException,
    NotFacingTargetException,
    ActorBusyException
)


class TestPhysicalMapHarvest:
    """PhysicalMapAggregateにおける採取アクションのテスト"""

    @pytest.fixture
    def map_aggregate(self):
        spot_id = SpotId(1)
        tiles = [
            Tile(Coordinate(0, 0, 0), TerrainType.grass()),
            Tile(Coordinate(1, 0, 0), TerrainType.grass()),
            Tile(Coordinate(2, 0, 0), TerrainType.grass()),
        ]
        return PhysicalMapAggregate.create(spot_id, tiles)

    @pytest.fixture
    def actor(self):
        return WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.EAST)
        )

    @pytest.fixture
    def resource(self):
        return WorldObject(
            object_id=WorldObjectId(200),
            coordinate=Coordinate(1, 0, 0),
            object_type=ObjectTypeEnum.RESOURCE,
            component=HarvestableComponent(
                loot_table_id=1,
                max_quantity=1,
                harvest_duration=10
            )
        )

    def test_start_harvest_success(self, map_aggregate, actor, resource):
        """採取開始の正常系テスト"""
        map_aggregate.add_object(actor)
        map_aggregate.add_object(resource)
        
        current_tick = WorldTick(100)
        map_aggregate.start_resource_harvest(actor.object_id, resource.object_id, current_tick)
        
        # アクターがビジー状態になっていること
        assert actor.is_busy(current_tick)
        assert actor.busy_until == WorldTick(110)
        
        # イベントが発行されていること
        events = map_aggregate.get_events()
        start_event = next(e for e in events if isinstance(e, HarvestStartedEvent))
        assert start_event.actor_id == actor.object_id
        assert start_event.target_id == resource.object_id
        assert start_event.finish_tick == WorldTick(110)

    def test_start_harvest_out_of_range(self, map_aggregate, actor, resource):
        """距離が離れている場合のテスト"""
        # アクターを (0,0)、リソースを (2,0) に配置
        actor = WorldObject(
            object_id=WorldObjectId(100),
            coordinate=Coordinate(0, 0, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.EAST)
        )
        resource = WorldObject(
            object_id=WorldObjectId(200),
            coordinate=Coordinate(2, 0, 0),
            object_type=ObjectTypeEnum.RESOURCE,
            component=HarvestableComponent(loot_table_id=1)
        )
        map_aggregate.add_object(actor)
        map_aggregate.add_object(resource)
        
        with pytest.raises(InteractionOutOfRangeException):
            map_aggregate.start_resource_harvest(actor.object_id, resource.object_id, WorldTick(100))

    def test_start_harvest_wrong_direction(self, map_aggregate, actor, resource):
        """向きが正しくない場合のテスト"""
        # アクターが西を向いている（リソースは東隣）
        actor.turn(DirectionEnum.WEST)
        map_aggregate.add_object(actor)
        map_aggregate.add_object(resource)
        
        with pytest.raises(NotFacingTargetException):
            map_aggregate.start_resource_harvest(actor.object_id, resource.object_id, WorldTick(100))

    def test_start_harvest_not_harvestable(self, map_aggregate, actor):
        """採取不可能なオブジェクトに対するテスト"""
        # 他のアクター（採取不可）をターゲットにする
        other_actor = WorldObject(
            object_id=WorldObjectId(101),
            coordinate=Coordinate(1, 0, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent()
        )
        map_aggregate.add_object(actor)
        map_aggregate.add_object(other_actor)
        
        with pytest.raises(NotHarvestableException):
            map_aggregate.start_resource_harvest(actor.object_id, other_actor.object_id, WorldTick(100))

    def test_finish_harvest_success(self, map_aggregate, actor, resource):
        """採取完了の正常系テスト"""
        map_aggregate.add_object(actor)
        map_aggregate.add_object(resource)
        
        start_tick = WorldTick(100)
        map_aggregate.start_resource_harvest(actor.object_id, resource.object_id, start_tick)
        
        # 10ティック経過後
        current_tick = WorldTick(110)
        map_aggregate.clear_events()
        map_aggregate.finish_resource_harvest(actor.object_id, resource.object_id, current_tick)
        
        # アクターのビジー状態が解除されていること
        assert not actor.is_busy(current_tick)
        
        # イベントが発行されていること
        events = map_aggregate.get_events()
        comp_event = next(e for e in events if isinstance(e, HarvestCompletedEvent))
        assert comp_event.actor_id == actor.object_id
        assert comp_event.target_id == resource.object_id
        assert comp_event.loot_table_id == LootTableId(1)
        
        # 資源が減少していること
        assert resource.component.get_available_quantity(current_tick) == 0

    def test_finish_harvest_too_early(self, map_aggregate, actor, resource):
        """時間が経過する前に完了させようとした場合のテスト"""
        map_aggregate.add_object(actor)
        map_aggregate.add_object(resource)
        
        map_aggregate.start_resource_harvest(actor.object_id, resource.object_id, WorldTick(100))
        
        # まだ9ティックしか経過していない
        map_aggregate.finish_resource_harvest(actor.object_id, resource.object_id, WorldTick(109))
        
        # イベントは発行されない
        events = map_aggregate.get_events()
        assert not any(isinstance(e, HarvestCompletedEvent) for e in events)
        
        # 資源も減少していない
        assert resource.component.get_available_quantity(WorldTick(109)) == 1

    def test_cancel_harvest(self, map_aggregate, actor, resource):
        """採取中断のテスト"""
        map_aggregate.add_object(actor)
        map_aggregate.add_object(resource)
        
        map_aggregate.start_resource_harvest(actor.object_id, resource.object_id, WorldTick(100))
        
        map_aggregate.clear_events()
        map_aggregate.cancel_resource_harvest(actor.object_id, resource.object_id, reason="interrupted")
        
        # アクターのビジー状態が解除されていること
        assert not actor.is_busy(WorldTick(100))
        
        # 資源の採取状態がリセットされていること
        assert resource.component.current_actor_id is None
        
        # イベントが発行されていること
        events = map_aggregate.get_events()
        cancel_event = next(e for e in events if isinstance(e, HarvestCancelledEvent))
        assert cancel_event.actor_id == actor.object_id
        assert cancel_event.reason == "interrupted"

    def test_concurrency_prevention(self, map_aggregate, actor, resource):
        """同時採取の防止テスト"""
        # (1,1,0) のタイルを追加
        map_aggregate._tiles[Coordinate(1, 1, 0)] = Tile(Coordinate(1, 1, 0), TerrainType.grass())
        
        actor2 = WorldObject(
            object_id=WorldObjectId(101),
            coordinate=Coordinate(1, 1, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.NORTH) # リソース(1,0,0)の方を向く
        )
        # actor2を (1,1) に配置し、下を向かせる
        map_aggregate.add_object(actor)
        map_aggregate.add_object(actor2)
        map_aggregate.add_object(resource)
        
        # actor1が開始
        map_aggregate.start_resource_harvest(actor.object_id, resource.object_id, WorldTick(100))
        
        # actor2が開始しようとすると失敗
        with pytest.raises(HarvestInProgressException):
            map_aggregate.start_resource_harvest(actor2.object_id, resource.object_id, WorldTick(100))

    def test_actor_busy_prevention(self, map_aggregate, actor, resource):
        """アクターがビジーな間に他の行動ができないことのテスト"""
        map_aggregate.add_object(actor)
        map_aggregate.add_object(resource)
        
        map_aggregate.start_resource_harvest(actor.object_id, resource.object_id, WorldTick(100))
        
        # ビジーなアクターは移動できない（東方向は(1,0,0)だがリソースがいるので、SOUTHへ）
        map_aggregate._tiles[Coordinate(0, 1, 0)] = Tile(Coordinate(0, 1, 0), TerrainType.grass())
        with pytest.raises(ActorBusyException):
            map_aggregate.move_actor(actor.object_id, DirectionEnum.SOUTH, WorldTick(105))
