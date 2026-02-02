import pytest
from ai_rpg_world.application.world.services.world_simulation_service import WorldSimulationApplicationService
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import InMemoryGameTimeProvider
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import InMemoryPhysicalMapRepository
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.unit_of_work.unit_of_work_factory_impl import InMemoryUnitOfWorkFactory
from ai_rpg_world.domain.world.service.behavior_service import BehaviorService
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.infrastructure.world.pathfinding.astar_pathfinding_strategy import AStarPathfindingStrategy
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, BehaviorStateEnum
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent
from ai_rpg_world.domain.common.value_object import WorldTick

class TestWorldSimulationApplicationService:
    """WorldSimulationApplicationServiceのテスト"""

    @pytest.fixture
    def setup_service(self):
        data_store = InMemoryDataStore()
        data_store.clear_all()
        
        time_provider = InMemoryGameTimeProvider(initial_tick=10)
        uow = InMemoryUnitOfWorkFactory().create()
        repository = InMemoryPhysicalMapRepository(data_store, uow)
        
        pathfinding_service = PathfindingService(AStarPathfindingStrategy())
        behavior_service = BehaviorService(pathfinding_service)
        
        service = WorldSimulationApplicationService(
            time_provider=time_provider,
            physical_map_repository=repository,
            behavior_service=behavior_service,
            unit_of_work=uow
        )
        
        return service, time_provider, repository, uow

    def test_tick_advances_time(self, setup_service):
        """tickによってゲーム時間が進むこと"""
        service, time_provider, _, _ = setup_service
        
        assert time_provider.get_current_tick() == WorldTick(10)
        
        new_tick = service.tick()
        
        assert new_tick == WorldTick(11)
        assert time_provider.get_current_tick() == WorldTick(11)

    def test_tick_updates_autonomous_actors(self, setup_service):
        """tickによって自律行動アクターの行動が計画・実行されること"""
        service, _, repository, _ = setup_service
        
        # マップのセットアップ
        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
        
        # アクターのセットアップ（巡回するアクター）
        actor_id = WorldObjectId(1)
        patrol_points = [Coordinate(2, 2)]
        behavior = AutonomousBehaviorComponent(
            state=BehaviorStateEnum.PATROL,
            patrol_points=patrol_points,
            random_move_chance=0.0 # 決定論的に動かす
        )
        actor = WorldObject(actor_id, Coordinate(0, 0), ObjectTypeEnum.NPC, component=behavior)
        
        physical_map = PhysicalMapAggregate.create(spot_id, tiles, objects=[actor])
        repository.save(physical_map)
        
        # 1ティック進める
        service.tick()
        
        # アクターが移動していることを確認
        updated_map = repository.find_by_spot_id(spot_id)
        updated_actor = updated_map.get_object(actor_id)
        
        # (0,0)から(2,2)へ向かって1歩進んでいるはず (例: 1,0 or 0,1 or 1,1)
        assert updated_actor.coordinate != Coordinate(0, 0)
        assert updated_actor.coordinate.distance_to(Coordinate(0, 0)) <= 2

    def test_busy_actor_is_skipped(self, setup_service):
        """Busy状態のアクターはシミュレーションでスキップされること"""
        service, _, repository, _ = setup_service
        
        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
        
        actor_id = WorldObjectId(1)
        behavior = AutonomousBehaviorComponent(
            state=BehaviorStateEnum.PATROL,
            patrol_points=[Coordinate(2, 2)],
            random_move_chance=0.0
        )
        # Busy状態（Tick 20まで）で作成
        actor = WorldObject(
            actor_id, 
            Coordinate(0, 0), 
            ObjectTypeEnum.NPC, 
            component=behavior,
            busy_until=WorldTick(20)
        )
        
        physical_map = PhysicalMapAggregate.create(spot_id, tiles, objects=[actor])
        repository.save(physical_map)
        
        # ティック11に進める (actorはまだBusy)
        service.tick()
        
        # アクターが移動していないことを確認
        updated_map = repository.find_by_spot_id(spot_id)
        updated_actor = updated_map.get_object(actor_id)
        assert updated_actor.coordinate == Coordinate(0, 0)
        
        # ティック20に進める（Busy解除されるタイミング）
        # 現在11なので、あと9ティック
        for _ in range(9):
            service.tick()
            
        # 解除直後のティックではまだ古い座標の可能性がある（実装により異なるが、今回はis_busyがfalseになったら動く）
        service.tick()
        
        updated_actor = repository.find_by_spot_id(spot_id).get_object(actor_id)
        assert updated_actor.coordinate != Coordinate(0, 0)

    def test_tick_handles_actor_error_gracefully(self, setup_service):
        """1つのアクターでエラーが発生しても他のアクターの更新が継続されること"""
        service, _, repository, _ = setup_service
        
        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
        
        # エラーを起こすアクター（移動先が通行不可になるように仕向けるのは難しいので、モック的なアプローチが必要だが、
        # ここではAggregateの制約に抵触させてエラーを出す）
        
        # アクター1: 正常
        actor1_id = WorldObjectId(1)
        actor1 = WorldObject(actor1_id, Coordinate(0, 0), ObjectTypeEnum.NPC, 
                             component=AutonomousBehaviorComponent(patrol_points=[Coordinate(1, 1)], random_move_chance=0.0))
        
        # アクター2: 重複座標などでエラーを誘発させる
        # (move_object内で例外が発生するようにする)
        actor2_id = WorldObjectId(2)
        actor2 = WorldObject(actor2_id, Coordinate(4, 4), ObjectTypeEnum.NPC,
                             component=AutonomousBehaviorComponent(patrol_points=[Coordinate(4, 4)], random_move_chance=0.0))
        
        physical_map = PhysicalMapAggregate.create(spot_id, tiles, objects=[actor1, actor2])
        repository.save(physical_map)
        
        # モックを使ってactor2の移動時に例外を投げるように仕込む
        import unittest.mock as mock
        with mock.patch.object(PhysicalMapAggregate, 'move_object', side_effect=[None, Exception("Simulated error")]):
            # 1回目(actor1)は成功、2回目(actor2)は失敗する想定
            service.tick()
            
        # サービス全体がクラッシュせず、actor1が(mockされているので移動はしてないが)処理されたことを確認
        # (実際にはログにエラーが出るが、例外はキャッチされているはず)
        # ここでは例外が上に飛んでこないことを確認
