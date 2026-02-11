import pytest
from ai_rpg_world.application.world.services.world_simulation_service import WorldSimulationApplicationService
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import InMemoryGameTimeProvider
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import InMemoryPhysicalMapRepository
from ai_rpg_world.infrastructure.repository.in_memory_weather_zone_repository import InMemoryWeatherZoneRepository
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import InMemoryPlayerStatusRepository
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.unit_of_work.unit_of_work_factory_impl import InMemoryUnitOfWorkFactory
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from ai_rpg_world.domain.world.service.behavior_service import BehaviorService
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.domain.world.service.weather_config_service import DefaultWeatherConfigService
from ai_rpg_world.domain.world.aggregate.weather_zone import WeatherZone
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.weather_zone_id import WeatherZoneId
from ai_rpg_world.domain.world.value_object.weather_zone_name import WeatherZoneName
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, BehaviorStateEnum
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent, ActorComponent
from ai_rpg_world.domain.common.value_object import WorldTick

class TestWorldSimulationApplicationService:
    @pytest.fixture
    def setup_service(self):
        data_store = InMemoryDataStore()
        data_store.clear_all()
        
        time_provider = InMemoryGameTimeProvider(initial_tick=10)
        
        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow, data_store=data_store)

        uow, event_publisher = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow,
            data_store=data_store
        )
        
        repository = InMemoryPhysicalMapRepository(data_store, uow)
        weather_zone_repo = InMemoryWeatherZoneRepository(data_store, uow)
        player_status_repo = InMemoryPlayerStatusRepository(data_store, uow)
        
        from ai_rpg_world.infrastructure.world.pathfinding.astar_pathfinding_strategy import AStarPathfindingStrategy
        pathfinding_service = PathfindingService(AStarPathfindingStrategy())
        behavior_service = BehaviorService(pathfinding_service)
        weather_config = DefaultWeatherConfigService(update_interval_ticks=1)
        
        service = WorldSimulationApplicationService(
            time_provider=time_provider,
            physical_map_repository=repository,
            weather_zone_repository=weather_zone_repo,
            player_status_repository=player_status_repo,
            behavior_service=behavior_service,
            weather_config_service=weather_config,
            unit_of_work=uow
        )
        
        return service, time_provider, repository, weather_zone_repo, player_status_repo, uow, event_publisher

    def test_tick_advances_time(self, setup_service):
        """tickによってゲーム時間が進むこと"""
        service, time_provider, _, _, _, _, _ = setup_service
        
        assert time_provider.get_current_tick() == WorldTick(10)
        
        service.tick()
        
        assert time_provider.get_current_tick() == WorldTick(11)

    def test_tick_updates_autonomous_actors(self, setup_service):
        """tickによって自律行動アクターの行動が計画・実行されること"""
        service, _, repository, _, _, _, _ = setup_service
        
        # マップのセットアップ
        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        
        # 自律行動アクターの追加
        actor_id = WorldObjectId(1)
        actor = WorldObject(
            actor_id, 
            Coordinate(2, 2), 
            ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(
                state=BehaviorStateEnum.PATROL,
                vision_range=5,
                patrol_points=[Coordinate(2, 2), Coordinate(2, 3)]
            )
        )
        physical_map.add_object(actor)
        repository.save(physical_map)
        
        # 1回実行
        service.tick()
        
        # アクターが移動している（またはビジーになっている）ことを確認
        updated_map = repository.find_by_spot_id(spot_id)
        updated_actor = updated_map.get_object(actor_id)
        
        # 移動したかビジー状態ならOK
        assert updated_actor.coordinate != Coordinate(2, 2) or updated_actor.is_busy(WorldTick(11))

    def test_busy_actor_is_skipped(self, setup_service):
        """Busy状態のアクターはシミュレーションでスキップされること"""
        service, _, repository, _, _, _, _ = setup_service
        
        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        
        # 最初からBusyなアクター
        actor_id = WorldObjectId(1)
        actor = WorldObject(
            actor_id, 
            Coordinate(2, 2), 
            ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(),
            busy_until=WorldTick(20) # Tick 20までBusy
        )
        physical_map.add_object(actor)
        repository.save(physical_map)
        
        # 1回実行 (Tick 11)
        service.tick()
        
        # アクターの状態が変わっていないことを確認
        updated_map = repository.find_by_spot_id(spot_id)
        updated_actor = updated_map.get_object(actor_id)
        assert updated_actor.coordinate == Coordinate(2, 2)
        assert updated_actor.busy_until == WorldTick(20)

    def test_tick_handles_actor_error_gracefully(self, setup_service):
        """1つのアクターでエラーが発生しても他のアクターの更新が継続されること"""
        service, _, repository, _, _, _, _ = setup_service
        
        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        
        # エラーを投げるようにBehaviorServiceをmock
        import unittest.mock as mock
        with mock.patch.object(service._behavior_service, 'plan_next_move', side_effect=Exception("Plan error")):
            # アクター追加
            actor1 = WorldObject(WorldObjectId(1), Coordinate(2, 2), ObjectTypeEnum.NPC, component=AutonomousBehaviorComponent())
            physical_map.add_object(actor1)
            repository.save(physical_map)
            
            # 実行
            service.tick()
        
        # サービス全体がクラッシュせず、actor1が(mockされているので移動はしてないが)処理されたことを確認
        # (実際にはログにエラーが出るが、例外はキャッチされているはず)
        # ここでは例外が上に飛んでこないことを確認

    def test_tick_applies_environmental_stamina_drain(self, setup_service):
        """過酷な天候下でプレイヤーのスタミナが減少すること（正常系）"""
        service, _, map_repo, zone_repo, player_repo, uow, _ = setup_service
        
        # 1. セットアップ: 吹雪のゾーン
        spot_id = SpotId(1)
        zone_id = WeatherZoneId(2)
        weather_state = WeatherState(WeatherTypeEnum.BLIZZARD, 1.0) # Drain = 3
        
        zone = WeatherZone.create(zone_id, WeatherZoneName("Arctic"), {spot_id}, weather_state)
        zone_repo.save(zone)
        
        tiles = [Tile(Coordinate(0, 0), TerrainType.grass())]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        map_repo.save(physical_map)
        
        # 2. プレイヤーの配置
        player_id = PlayerId(100)
        player_status = self._create_sample_player(player_id, spot_id, Coordinate(0, 0), stamina_val=100)
        player_repo.save(player_status)
        
        # 物理マップにアクターとして登録（正式にplayer_idを紐付け）
        actor = WorldObject(
            WorldObjectId(100), 
            Coordinate(0, 0), 
            ObjectTypeEnum.PLAYER,
            component=ActorComponent(player_id=player_id)
        )
        physical_map.add_object(actor)
        map_repo.save(physical_map)
        
        # 3. ティック実行
        import unittest.mock as mock
        from ai_rpg_world.domain.world.service.weather_simulation_service import WeatherSimulationService
        
        with mock.patch.object(WeatherSimulationService, 'simulate_next_weather', return_value=weather_state):
            service.tick()
        
        # 4. スタミナが減っていることを確認 (100 -> 97)
        updated_player = player_repo.find_by_id(player_id)
        assert updated_player.stamina.value == 97

    def test_environmental_drain_skips_non_player_actors(self, setup_service):
        """NPCなどのプレイヤー以外の項目には環境ダメージが適用されないこと"""
        service, _, map_repo, zone_repo, player_repo, _, _ = setup_service
        
        spot_id = SpotId(1)
        weather_state = WeatherState(WeatherTypeEnum.BLIZZARD, 1.0) # Drain = 3
        zone = WeatherZone.create(WeatherZoneId(1), WeatherZoneName("Zone"), {spot_id}, weather_state)
        zone_repo.save(zone)
        
        physical_map = PhysicalMapAggregate.create(spot_id, [Tile(Coordinate(0, 0), TerrainType.grass())])
        
        # プレイヤーIDのないアクター
        npc_actor = WorldObject(
            WorldObjectId(500), 
            Coordinate(0, 0), 
            ObjectTypeEnum.NPC,
            component=ActorComponent(player_id=None)
        )
        physical_map.add_object(npc_actor)
        map_repo.save(physical_map)
        
        # エラーが発生せず、正常に終了することを確認
        service.tick()
        
    def test_stamina_drain_not_below_zero(self, setup_service):
        """スタミナ減少によってスタミナが負の値にならないこと（境界値）"""
        service, _, map_repo, zone_repo, player_repo, _, _ = setup_service
        
        spot_id = SpotId(1)
        weather_state = WeatherState(WeatherTypeEnum.BLIZZARD, 1.0) # Drain = 3
        zone = WeatherZone.create(WeatherZoneId(1), WeatherZoneName("Zone"), {spot_id}, weather_state)
        zone_repo.save(zone)
        
        physical_map = PhysicalMapAggregate.create(spot_id, [Tile(Coordinate(0, 0), TerrainType.grass())])
        
        # スタミナが残り少ない（1）プレイヤー
        player_id = PlayerId(101)
        player_status = self._create_sample_player(player_id, spot_id, Coordinate(0, 0), stamina_val=1)
        player_repo.save(player_status)
        
        actor = WorldObject(WorldObjectId(101), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                             component=ActorComponent(player_id=player_id))
        physical_map.add_object(actor)
        map_repo.save(physical_map)
        
        # 実行 (天候が変わらないようにモック)
        import unittest.mock as mock
        from ai_rpg_world.domain.world.service.weather_simulation_service import WeatherSimulationService
        with mock.patch.object(WeatherSimulationService, 'simulate_next_weather', return_value=weather_state):
            service.tick()
        
        # スタミナが0になっている（マイナスにならない）
        updated_player = player_repo.find_by_id(player_id)
        assert updated_player.stamina.value == 0

    def test_handles_missing_player_status_gracefully(self, setup_service):
        """アクターにplayer_idはあるが、リポジトリにステータスがない場合にエラーにならないこと（異常系）"""
        service, _, map_repo, zone_repo, _, _, _ = setup_service
        
        spot_id = SpotId(1)
        zone_repo.save(WeatherZone.create(WeatherZoneId(1), WeatherZoneName("Z"), {spot_id}, WeatherState(WeatherTypeEnum.BLIZZARD, 1.0)))
        
        physical_map = PhysicalMapAggregate.create(spot_id, [Tile(Coordinate(0, 0), TerrainType.grass())])
        
        # 存在しないPlayerIdを指定
        actor = WorldObject(WorldObjectId(999), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                             component=ActorComponent(player_id=PlayerId(999)))
        physical_map.add_object(actor)
        map_repo.save(physical_map)
        
        # ログに警告が出るが、プロセスは継続すること
        service.tick()

    def test_handles_missing_weather_zone_gracefully(self, setup_service):
        """マップに対応する天候ゾーンがない場合、デフォルト（晴れ）として処理されること（異常系）"""
        service, _, map_repo, zone_repo, player_repo, _, _ = setup_service
        
        # ゾーンを登録しない
        spot_id = SpotId(1)
        physical_map = PhysicalMapAggregate.create(spot_id, [Tile(Coordinate(0, 0), TerrainType.grass())])
        
        # プレイヤー配置
        player_id = PlayerId(200)
        player_status = self._create_sample_player(player_id, spot_id, Coordinate(0, 0), stamina_val=100)
        player_repo.save(player_status)
        physical_map.add_object(WorldObject(WorldObjectId(200), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                                           component=ActorComponent(player_id=player_id)))
        map_repo.save(physical_map)
        
        # 実行
        service.tick()
        
        # 天候がClearになっている
        updated_map = map_repo.find_by_spot_id(spot_id)
        assert updated_map.weather_state.weather_type == WeatherTypeEnum.CLEAR
        # スタミナも減っていない
        assert player_repo.find_by_id(player_id).stamina.value == 100

    def test_weather_update_respects_interval(self, setup_service):
        """天候更新が設定されたインターバルに従うこと（ロジック検証）"""
        service, time_provider, map_repo, zone_repo, _, _, _ = setup_service
        
        # インターバルを5に設定
        from ai_rpg_world.domain.world.service.weather_config_service import DefaultWeatherConfigService
        service._weather_config_service = DefaultWeatherConfigService(update_interval_ticks=5)
        
        spot_id = SpotId(1)
        zone_id = WeatherZoneId(1)
        zone = WeatherZone.create(zone_id, WeatherZoneName("Z"), {spot_id}, WeatherState(WeatherTypeEnum.CLEAR, 1.0))
        zone_repo.save(zone)
        
        physical_map = PhysicalMapAggregate.create(spot_id, [Tile(Coordinate(0, 0), TerrainType.grass())])
        map_repo.save(physical_map)
        
        # Tick 10 (現在) -> service.tick() -> advance_tick() -> Tick 11
        # 11 % 5 != 0 なので更新されない。
        # 更新させるためには、Tick 14 で呼び出す必要がある (14 -> 15 % 5 == 0)
        time_provider.advance_tick(4) # 10 -> 14
        
        import unittest.mock as mock
        from ai_rpg_world.domain.world.service.weather_simulation_service import WeatherSimulationService
        new_state = WeatherState(WeatherTypeEnum.CLOUDY, 1.0)
        
        with mock.patch.object(WeatherSimulationService, 'simulate_next_weather', return_value=new_state):
            service.tick() # Tick 15
        
        assert zone_repo.find_by_id(zone_id).current_state.weather_type == WeatherTypeEnum.CLOUDY
        
        # Tick 16, 17, 18, 19 は更新されない
        for _ in range(4):
            service.tick() # Tick 16, 17, 18, 19
            assert zone_repo.find_by_id(zone_id).current_state.weather_type == WeatherTypeEnum.CLOUDY

        # 次の更新は Tick 20 (CLOUDY -> RAIN は許可されている)
        new_state2 = WeatherState(WeatherTypeEnum.RAIN, 1.0)
        with mock.patch.object(WeatherSimulationService, 'simulate_next_weather', return_value=new_state2):
            service.tick() # Tick 20
            
        assert zone_repo.find_by_id(zone_id).current_state.weather_type == WeatherTypeEnum.RAIN

    def test_stamina_drain_publishes_events_to_uow(self, setup_service):
        """スタミナ減少イベントがUnitOfWorkに追加されること"""
        service, _, map_repo, zone_repo, player_repo, uow, event_publisher = setup_service
        
        spot_id = SpotId(1)
        weather_state = WeatherState(WeatherTypeEnum.BLIZZARD, 1.0)
        zone_repo.save(WeatherZone.create(WeatherZoneId(1), WeatherZoneName("Z"), {spot_id}, weather_state))
        
        physical_map = PhysicalMapAggregate.create(spot_id, [Tile(Coordinate(0, 0), TerrainType.grass())])
        map_repo.save(physical_map)
        
        player_id = PlayerId(100)
        player_status = self._create_sample_player(player_id, spot_id, Coordinate(0, 0), stamina_val=100)
        player_repo.save(player_status)
        
        actor = WorldObject(WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER, component=ActorComponent(player_id=player_id))
        physical_map.add_object(actor)
        map_repo.save(physical_map)
        
        # 実行 (天候が変わらないようにモック)
        import unittest.mock as mock
        from ai_rpg_world.domain.world.service.weather_simulation_service import WeatherSimulationService
        with mock.patch.object(WeatherSimulationService, 'simulate_next_weather', return_value=weather_state):
            service.tick()
        
        # published_eventsを確認
        from ai_rpg_world.domain.player.event.status_events import PlayerStaminaConsumedEvent
        events = event_publisher.get_published_events()
        assert any(isinstance(e, PlayerStaminaConsumedEvent) for e in events)

    def test_bulk_processing_handles_partial_failures(self, setup_service):
        """バルク処理中に一部のプレイヤーでエラー（ドメイン例外など）が発生しても他が正常に処理されること"""
        service, _, map_repo, zone_repo, player_repo, _, _ = setup_service
        
        spot_id = SpotId(1)
        weather_state = WeatherState(WeatherTypeEnum.BLIZZARD, 1.0) # Drain = 3
        zone_repo.save(WeatherZone.create(WeatherZoneId(1), WeatherZoneName("Z"), {spot_id}, weather_state))
        
        physical_map = PhysicalMapAggregate.create(spot_id, [
            Tile(Coordinate(0, 0), TerrainType.grass()),
            Tile(Coordinate(1, 1), TerrainType.grass())
        ])
        map_repo.save(physical_map)
        
        # プレイヤー1: 正常
        pid1 = PlayerId(1)
        ps1 = self._create_sample_player(pid1, spot_id, Coordinate(0, 0), stamina_val=100)
        player_repo.save(ps1)
        physical_map.add_object(WorldObject(WorldObjectId(1), Coordinate(0, 0), ObjectTypeEnum.PLAYER, component=ActorComponent(player_id=pid1)))
        
        # プレイヤー2: 戦闘不能（本来はcan_actで弾かれるが、テストのため）
        pid2 = PlayerId(2)
        ps2 = self._create_sample_player(pid2, spot_id, Coordinate(1, 1), stamina_val=100)
        ps2.apply_damage(1000) # is_down = True
        player_repo.save(ps2)
        physical_map.add_object(WorldObject(WorldObjectId(2), Coordinate(1, 1), ObjectTypeEnum.PLAYER, component=ActorComponent(player_id=pid2)))
        
        map_repo.save(physical_map)
        
        # 実行 (天候が変わらないようにモック)
        import unittest.mock as mock
        from ai_rpg_world.domain.world.service.weather_simulation_service import WeatherSimulationService
        with mock.patch.object(WeatherSimulationService, 'simulate_next_weather', return_value=weather_state):
            service.tick()
        
        # プレイヤー1はスタミナ減少
        assert player_repo.find_by_id(pid1).stamina.value == 97
        # プレイヤー2は変化なし（can_act() == False のためスキップされる）
        assert player_repo.find_by_id(pid2).stamina.value == 100

    def _create_sample_player(self, player_id, spot_id, coord, stamina_val=100):
        base_stats = BaseStats(100, 50, 10, 10, 10, 0.05, 0.05)
        exp_table = ExpTable(100.0, 2.0)
        return PlayerStatusAggregate(
            player_id=player_id,
            base_stats=base_stats,
            stat_growth_factor=StatGrowthFactor.for_level(1),
            exp_table=exp_table,
            growth=Growth(1, 0, exp_table),
            gold=Gold(0),
            hp=Hp.create(100, 100),
            mp=Mp.create(50, 50),
            stamina=Stamina.create(stamina_val, 100),
            current_spot_id=spot_id,
            current_coordinate=coord
        )
