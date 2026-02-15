import pytest
import unittest.mock as mock
from ai_rpg_world.application.world.services.world_simulation_service import WorldSimulationApplicationService
from ai_rpg_world.application.world.services.caching_pathfinding_service import CachingPathfindingService
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import InMemoryGameTimeProvider
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import InMemoryPhysicalMapRepository
from ai_rpg_world.infrastructure.repository.in_memory_weather_zone_repository import InMemoryWeatherZoneRepository
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import InMemoryPlayerStatusRepository
from ai_rpg_world.infrastructure.repository.in_memory_hit_box_repository import InMemoryHitBoxRepository
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.unit_of_work.unit_of_work_factory_impl import InMemoryUnitOfWorkFactory
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from ai_rpg_world.domain.world.service.behavior_service import BehaviorService
from ai_rpg_world.domain.world.service.hostility_service import ConfigurableHostilityService
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.domain.world.service.weather_config_service import DefaultWeatherConfigService
from ai_rpg_world.domain.world.service.world_time_config_service import DefaultWorldTimeConfigService
from ai_rpg_world.domain.world.enum.world_enum import ActiveTimeType
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterStatusEnum
from ai_rpg_world.domain.monster.value_object.spawn_condition import SpawnCondition
from ai_rpg_world.domain.world.value_object.time_of_day import TimeOfDay
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
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, BehaviorStateEnum, DirectionEnum, BehaviorActionType
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.value_object.behavior_action import BehaviorAction
from ai_rpg_world.application.common.exceptions import ApplicationException, SystemErrorException
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
from ai_rpg_world.domain.monster.service.monster_skill_execution_domain_service import MonsterSkillExecutionDomainService
from ai_rpg_world.infrastructure.repository.in_memory_monster_aggregate_repository import InMemoryMonsterAggregateRepository
from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
from ai_rpg_world.domain.monster.enum.monster_enum import MonsterFactionEnum
from ai_rpg_world.domain.player.enum.player_enum import Race, Element
from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import SkillLoadoutAggregate
from ai_rpg_world.domain.skill.value_object.skill_loadout_id import SkillLoadoutId
from ai_rpg_world.domain.skill.value_object.skill_id import SkillId
from ai_rpg_world.domain.skill.value_object.skill_spec import SkillSpec
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier, SkillHitPatternType
from ai_rpg_world.domain.skill.value_object.skill_hit_pattern import SkillHitPattern
from ai_rpg_world.domain.skill.service.skill_execution_service import SkillExecutionDomainService
from ai_rpg_world.domain.skill.service.skill_to_hitbox_service import SkillToHitBoxDomainService
from ai_rpg_world.domain.skill.service.skill_targeting_service import SkillTargetingDomainService
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent, ActorComponent, MonsterSkillInfo
from ai_rpg_world.domain.world.value_object.behavior_context import (
    SkillSelectionContext,
    TargetSelectionContext,
    GrowthContext,
)
from ai_rpg_world.domain.world.value_object.aggro_memory_policy import AggroMemoryPolicy
from ai_rpg_world.infrastructure.aggro.in_memory_aggro_store import InMemoryAggroStore
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.combat.aggregate.hit_box_aggregate import HitBoxAggregate
from ai_rpg_world.domain.combat.value_object.hit_box_id import HitBoxId
from ai_rpg_world.domain.combat.value_object.hit_box_shape import HitBoxShape
from ai_rpg_world.domain.combat.value_object.hit_box_velocity import HitBoxVelocity
from ai_rpg_world.domain.combat.value_object.hit_box_collision_policy import (
    ObstacleCollisionPolicy,
    TargetCollisionPolicy,
)
from ai_rpg_world.domain.combat.service.hit_box_config_service import DefaultHitBoxConfigService
from ai_rpg_world.domain.combat.service.hit_box_collision_service import HitBoxCollisionDomainService
from ai_rpg_world.domain.combat.event.combat_events import (
    HitBoxMovedEvent,
    HitBoxHitRecordedEvent,
    HitBoxObstacleCollidedEvent,
    HitBoxDeactivatedEvent,
)


class _InMemorySkillLoadoutRepo:
    """テスト用のスキルロードアウト保存（WorldSimulation は save のみ使用）"""
    def __init__(self):
        self._data = {}

    def save(self, loadout):
        self._data[loadout.loadout_id] = loadout

    def find_by_id(self, loadout_id):
        return self._data.get(loadout_id)


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
        hit_box_repo = InMemoryHitBoxRepository(data_store, uow)
        
        from ai_rpg_world.infrastructure.world.pathfinding.astar_pathfinding_strategy import AStarPathfindingStrategy
        pathfinding_service = PathfindingService(AStarPathfindingStrategy())
        caching_pathfinding = CachingPathfindingService(
            pathfinding_service,
            time_provider=time_provider,
            ttl_ticks=5,
        )
        behavior_service = BehaviorService(caching_pathfinding)
        weather_config = DefaultWeatherConfigService(update_interval_ticks=1)
        hit_box_config = DefaultHitBoxConfigService(substeps_per_tick=4)
        hit_box_collision_service = HitBoxCollisionDomainService()
        
        # モンスター・スキルロードアウト・ドメインサービス・ファクトリ
        monster_repo = InMemoryMonsterAggregateRepository(data_store, uow)
        skill_loadout_repo = _InMemorySkillLoadoutRepo()
        skill_execution_service = SkillExecutionDomainService(
            SkillTargetingDomainService(),
            SkillToHitBoxDomainService(),
        )
        monster_skill_execution_domain_service = MonsterSkillExecutionDomainService(skill_execution_service)
        from ai_rpg_world.domain.combat.service.hit_box_factory import HitBoxFactory
        hit_box_factory = HitBoxFactory()

        service = WorldSimulationApplicationService(
            time_provider=time_provider,
            physical_map_repository=repository,
            weather_zone_repository=weather_zone_repo,
            player_status_repository=player_status_repo,
            hit_box_repository=hit_box_repo,
            behavior_service=behavior_service,
            weather_config_service=weather_config,
            unit_of_work=uow,
            monster_repository=monster_repo,
            skill_loadout_repository=skill_loadout_repo,
            monster_skill_execution_domain_service=monster_skill_execution_domain_service,
            hit_box_factory=hit_box_factory,
            hit_box_config_service=hit_box_config,
            hit_box_collision_service=hit_box_collision_service,
            world_time_config_service=DefaultWorldTimeConfigService(ticks_per_day=24),
        )
        
        return service, time_provider, repository, weather_zone_repo, player_status_repo, hit_box_repo, uow, event_publisher, monster_repo, skill_loadout_repo

    def test_tick_advances_time(self, setup_service):
        """tickによってゲーム時間が進むこと"""
        service, time_provider, _, _, _, _, _, _, _, _ = setup_service
        
        assert time_provider.get_current_tick() == WorldTick(10)
        
        service.tick()
        
        assert time_provider.get_current_tick() == WorldTick(11)

    def test_tick_updates_autonomous_actors(self, setup_service):
        """tickによって自律行動アクターの行動が計画・実行されること（アクティブスポットのみ更新）"""
        service, _, repository, _, _, _, _, _, _, _ = setup_service
        
        # マップのセットアップ（プレイヤーがいるスポットのみ更新されるためプレイヤーを配置）
        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        physical_map.add_object(WorldObject(
            WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
            component=ActorComponent(player_id=PlayerId(100)),
        ))
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
        service, _, repository, _, _, _, _, _, _, _ = setup_service
        
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
        service, _, repository, _, _, _, _, _, _, _ = setup_service
        
        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        physical_map.add_object(WorldObject(
            WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
            component=ActorComponent(player_id=PlayerId(100)),
        ))
        actor1_id = WorldObjectId(1)
        actor2_id = WorldObjectId(2)
        actor1 = WorldObject(
            actor1_id, Coordinate(2, 2), ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(state=BehaviorStateEnum.PATROL, patrol_points=[Coordinate(2, 2), Coordinate(2, 3)])
        )
        actor2 = WorldObject(
            actor2_id, Coordinate(3, 3), ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(state=BehaviorStateEnum.PATROL, patrol_points=[Coordinate(3, 3), Coordinate(3, 4)])
        )
        physical_map.add_object(actor1)
        physical_map.add_object(actor2)
        repository.save(physical_map)
        
        player_wo_id = WorldObjectId(100)
        call_count = [0]
        def plan_action_side_effect(actor_id_arg, map_agg, **kwargs):
            call_count[0] += 1
            if actor_id_arg == player_wo_id:
                return BehaviorAction.wait()
            if actor_id_arg == actor1_id:
                raise Exception("Plan error")
            return BehaviorAction.move(Coordinate(3, 4))
        
        import unittest.mock as mock
        with mock.patch.object(service._behavior_service, "plan_action", side_effect=plan_action_side_effect):
            service.tick()
        
        updated_map = repository.find_by_spot_id(spot_id)
        assert call_count[0] == 3
        assert updated_map.get_object(actor1_id).coordinate == Coordinate(2, 2)
        assert updated_map.get_object(actor2_id).coordinate == Coordinate(3, 4)

    def test_tick_domain_exception_converted_to_application_exception(self, setup_service):
        """tick内でDomainExceptionが発生した場合、ApplicationExceptionに変換されて送出されること"""
        service, _, _, _, _, _, _, _, _, _ = setup_service

        with mock.patch.object(
            service._physical_map_repository,
            "find_all",
            side_effect=DomainException("domain rule violation"),
        ):
            with pytest.raises(ApplicationException) as excinfo:
                service.tick()
        assert "domain rule violation" in str(excinfo.value)
        assert excinfo.value.cause is not None
        assert isinstance(excinfo.value.cause, DomainException)

    def test_tick_unexpected_exception_raises_system_error_exception(self, setup_service):
        """tick内で予期しない例外が発生した場合、SystemErrorExceptionが送出されること"""
        service, _, _, _, _, _, _, _, _, _ = setup_service

        with mock.patch.object(
            service._physical_map_repository,
            "find_all",
            side_effect=RuntimeError("repo error"),
        ):
            with pytest.raises(SystemErrorException) as excinfo:
                service.tick()
        assert "tick" in str(excinfo.value).lower()
        assert "failed" in str(excinfo.value).lower()
        assert excinfo.value.original_exception is not None
        assert isinstance(excinfo.value.original_exception, RuntimeError)

    def test_tick_raises_application_exception_when_use_skill_has_no_slot_index(self, setup_service):
        """USE_SKILLアクションでskill_slot_indexがNoneの場合にApplicationExceptionが発生すること"""
        service, _, repository, _, _, _, _, _, _, _ = setup_service
        
        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        physical_map.add_object(WorldObject(
            WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
            component=ActorComponent(player_id=PlayerId(100)),
        ))
        actor_id = WorldObjectId(1)
        physical_map.add_object(WorldObject(
            actor_id, Coordinate(2, 2), ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent()
        ))
        repository.save(physical_map)
        
        invalid_action = BehaviorAction(
            action_type=BehaviorActionType.USE_SKILL,
            coordinate=None,
            skill_slot_index=None,
        )
        with mock.patch.object(service._behavior_service, "plan_action", return_value=invalid_action):
            with pytest.raises(ApplicationException, match="skill_slot_index"):
                service.tick()

    def test_tick_applies_environmental_stamina_drain(self, setup_service):
        """過酷な天候下でプレイヤーのスタミナが減少すること（正常系）"""
        service, _, map_repo, zone_repo, player_repo, _, uow, _, _, _ = setup_service
        
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
        service, _, map_repo, zone_repo, player_repo, _, _, _, _, _ = setup_service
        
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
        service, _, map_repo, zone_repo, player_repo, _, _, _, _, _ = setup_service
        
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
        service, _, map_repo, zone_repo, _, _, _, _, _, _ = setup_service
        
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
        service, _, map_repo, zone_repo, player_repo, _, _, _, _, _ = setup_service
        
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
        service, time_provider, map_repo, zone_repo, _, _, _, _, _, _ = setup_service
        
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
        service, _, map_repo, zone_repo, player_repo, _, uow, event_publisher, _, _ = setup_service
        
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
        service, _, map_repo, zone_repo, player_repo, _, _, _, _, _ = setup_service
        
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

    def test_tick_updates_hitbox_and_records_target_hit_event(self, setup_service):
        """tickでHitBoxが移動し、同座標のオブジェクトへのヒットイベントが発行されること"""
        service, _, map_repo, _, _, hit_box_repo, _, event_publisher, _, _ = setup_service

        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(4) for y in range(4)]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        physical_map.add_object(WorldObject(
            WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
            component=ActorComponent(player_id=PlayerId(100)),
        ))
        owner_id = WorldObjectId(900)
        target_id = WorldObjectId(901)
        owner = WorldObject(owner_id, Coordinate(0, 1), ObjectTypeEnum.NPC, component=AutonomousBehaviorComponent())
        target = WorldObject(target_id, Coordinate(1, 1), ObjectTypeEnum.NPC, component=AutonomousBehaviorComponent())
        physical_map.add_object(owner)
        physical_map.add_object(target)
        map_repo.save(physical_map)

        hit_box = HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(1),
            spot_id=spot_id,
            owner_id=owner_id,
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0, 1, 0),
            start_tick=WorldTick(10),
            duration=10,
            velocity=HitBoxVelocity(1, 0, 0),
        )
        hit_box_repo.save(hit_box)

        service.tick()  # tick 11

        updated = hit_box_repo.find_by_id(HitBoxId.create(1))
        assert updated.current_coordinate == Coordinate(1, 1, 0)
        assert updated.has_hit(target_id) is True

        events = event_publisher.get_published_events()
        assert any(isinstance(e, HitBoxMovedEvent) for e in events)
        assert any(isinstance(e, HitBoxHitRecordedEvent) for e in events)

    def test_tick_deactivates_hitbox_on_obstacle_when_policy_is_deactivate(self, setup_service):
        """障害物衝突でDEACTIVATEポリシーのHitBoxが消失すること"""
        service, _, map_repo, _, _, hit_box_repo, _, event_publisher, _, _ = setup_service

        spot_id = SpotId(1)
        tiles = [
            Tile(Coordinate(0, 0), TerrainType.grass()),
            Tile(Coordinate(1, 0), TerrainType.wall()),
            Tile(Coordinate(0, 1), TerrainType.grass()),
        ]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        physical_map.add_object(WorldObject(
            WorldObjectId(100), Coordinate(0, 1), ObjectTypeEnum.PLAYER,
            component=ActorComponent(player_id=PlayerId(100)),
        ))
        owner_id = WorldObjectId(910)
        physical_map.add_object(WorldObject(owner_id, Coordinate(0, 0), ObjectTypeEnum.NPC, component=AutonomousBehaviorComponent()))
        map_repo.save(physical_map)

        hit_box = HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(2),
            spot_id=spot_id,
            owner_id=owner_id,
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0, 0, 0),
            start_tick=WorldTick(10),
            duration=10,
            velocity=HitBoxVelocity(1, 0, 0),
            obstacle_collision_policy=ObstacleCollisionPolicy.DEACTIVATE,
        )
        hit_box_repo.save(hit_box)

        service.tick()

        updated = hit_box_repo.find_by_id(HitBoxId.create(2))
        assert updated.is_active is False

        events = event_publisher.get_published_events()
        assert any(isinstance(e, HitBoxObstacleCollidedEvent) for e in events)
        assert any(isinstance(e, HitBoxDeactivatedEvent) and e.reason == "obstacle_collision" for e in events)

    def test_tick_keeps_hitbox_active_when_obstacle_policy_pass_through(self, setup_service):
        """障害物衝突でもPASS_THROUGHポリシーのHitBoxは継続すること"""
        service, _, map_repo, _, _, hit_box_repo, _, event_publisher, _, _ = setup_service

        spot_id = SpotId(1)
        tiles = [
            Tile(Coordinate(0, 0), TerrainType.grass()),
            Tile(Coordinate(1, 0), TerrainType.wall()),
            Tile(Coordinate(0, 1), TerrainType.grass()),
        ]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        physical_map.add_object(WorldObject(
            WorldObjectId(100), Coordinate(0, 1), ObjectTypeEnum.PLAYER,
            component=ActorComponent(player_id=PlayerId(100)),
        ))
        owner_id = WorldObjectId(920)
        physical_map.add_object(WorldObject(owner_id, Coordinate(0, 0), ObjectTypeEnum.NPC, component=AutonomousBehaviorComponent()))
        map_repo.save(physical_map)

        hit_box = HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(3),
            spot_id=spot_id,
            owner_id=owner_id,
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0, 0, 0),
            start_tick=WorldTick(10),
            duration=10,
            velocity=HitBoxVelocity(1, 0, 0),
            obstacle_collision_policy=ObstacleCollisionPolicy.PASS_THROUGH,
        )
        hit_box_repo.save(hit_box)

        service.tick()

        updated = hit_box_repo.find_by_id(HitBoxId.create(3))
        assert updated.is_active is True
        assert updated.current_coordinate == Coordinate(1, 0, 0)

        events = event_publisher.get_published_events()
        assert any(isinstance(e, HitBoxObstacleCollidedEvent) for e in events)
        assert not any(isinstance(e, HitBoxDeactivatedEvent) and e.reason == "obstacle_collision" for e in events)

    def test_tick_deactivates_hitbox_on_target_collision_policy(self, setup_service):
        """ターゲット衝突でDEACTIVATEポリシーのHitBoxが消失すること"""
        service, _, map_repo, _, _, hit_box_repo, _, _, _, _ = setup_service

        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(2) for y in range(2)]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        physical_map.add_object(WorldObject(
            WorldObjectId(100), Coordinate(0, 1), ObjectTypeEnum.PLAYER,
            component=ActorComponent(player_id=PlayerId(100)),
        ))
        owner_id = WorldObjectId(930)
        target_id = WorldObjectId(931)
        physical_map.add_object(WorldObject(owner_id, Coordinate(0, 0), ObjectTypeEnum.NPC, component=AutonomousBehaviorComponent()))
        physical_map.add_object(WorldObject(target_id, Coordinate(1, 0), ObjectTypeEnum.NPC, component=AutonomousBehaviorComponent()))
        map_repo.save(physical_map)

        hit_box = HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(4),
            spot_id=spot_id,
            owner_id=owner_id,
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0, 0, 0),
            start_tick=WorldTick(10),
            duration=10,
            velocity=HitBoxVelocity(1, 0, 0),
            target_collision_policy=TargetCollisionPolicy.DEACTIVATE,
        )
        hit_box_repo.save(hit_box)

        service.tick()

        updated = hit_box_repo.find_by_id(HitBoxId.create(4))
        assert updated.has_hit(target_id) is True
        assert updated.is_active is False

    def test_tick_handles_hitbox_repository_failure_gracefully(self, setup_service):
        """HitBox更新処理で例外が発生してもtick全体は継続すること"""
        service, _, map_repo, _, _, _, _, _, _, _ = setup_service

        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(0, 0), TerrainType.grass()), Tile(Coordinate(0, 1), TerrainType.grass())]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        physical_map.add_object(WorldObject(
            WorldObjectId(100), Coordinate(0, 1), ObjectTypeEnum.PLAYER,
            component=ActorComponent(player_id=PlayerId(100)),
        ))
        map_repo.save(physical_map)

        import unittest.mock as mock
        with mock.patch.object(service._hit_box_repository, "find_active_by_spot_id", side_effect=Exception("repo error")):
            # 例外を外に投げず継続すること
            service.tick()

    def test_substep_update_accumulates_fractional_velocity_across_ticks(self, setup_service):
        """サブステップ更新で小数速度がティックをまたいで蓄積されること"""
        service, _, map_repo, _, _, hit_box_repo, _, _, _, _ = setup_service

        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(3) for y in range(2)]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        physical_map.add_object(WorldObject(
            WorldObjectId(100), Coordinate(2, 1), ObjectTypeEnum.PLAYER,
            component=ActorComponent(player_id=PlayerId(100)),
        ))
        owner_id = WorldObjectId(940)
        target_id = WorldObjectId(941)
        physical_map.add_object(WorldObject(owner_id, Coordinate(0, 0), ObjectTypeEnum.NPC, component=AutonomousBehaviorComponent()))
        physical_map.add_object(WorldObject(target_id, Coordinate(1, 0), ObjectTypeEnum.NPC, component=AutonomousBehaviorComponent()))
        map_repo.save(physical_map)

        hit_box = HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(5),
            spot_id=spot_id,
            owner_id=owner_id,
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0, 0, 0),
            start_tick=WorldTick(10),
            duration=10,
            velocity=HitBoxVelocity(0.5, 0.0, 0.0),
        )
        hit_box_repo.save(hit_box)

        service.tick()  # tick 11: precise 0.5, discrete 0
        updated = hit_box_repo.find_by_id(HitBoxId.create(5))
        assert updated.current_coordinate == Coordinate(0, 0, 0)
        assert updated.has_hit(target_id) is False
        assert updated.precise_position == pytest.approx((0.5, 0.0, 0.0))

        service.tick()  # tick 12: precise 1.0, discrete 1
        updated2 = hit_box_repo.find_by_id(HitBoxId.create(5))
        assert updated2.current_coordinate == Coordinate(1, 0, 0)
        assert updated2.has_hit(target_id) is True

    def test_substep_update_obstacle_collision_only_one_event(self, setup_service):
        """サブステップ更新で同じ障害物に複数回当たってもイベントは1度だけ発行されること"""
        service, _, map_repo, _, _, hit_box_repo, _, event_publisher, _, _ = setup_service

        spot_id = SpotId(1)
        # (1,0) が壁
        tiles = [
            Tile(Coordinate(0, 0), TerrainType.grass()),
            Tile(Coordinate(1, 0), TerrainType.wall()),
            Tile(Coordinate(0, 1), TerrainType.grass()),
        ]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        physical_map.add_object(WorldObject(
            WorldObjectId(100), Coordinate(0, 1), ObjectTypeEnum.PLAYER,
            component=ActorComponent(player_id=PlayerId(100)),
        ))
        owner_id = WorldObjectId(950)
        physical_map.add_object(WorldObject(owner_id, Coordinate(0, 0), ObjectTypeEnum.NPC, component=AutonomousBehaviorComponent()))
        map_repo.save(physical_map)

        # 速度 0.25 で 4サブステップ。各ステップで (0,0) -> (0,0) -> (0,0) -> (1,0) と移動し、
        # 最後のステップで壁に当たる。
        # 実際には substep ごとに衝突判定される。
        hit_box = HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(6),
            spot_id=spot_id,
            owner_id=owner_id,
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0, 0, 0),
            start_tick=WorldTick(10),
            duration=10,
            velocity=HitBoxVelocity(1.0, 0.0, 0.0),
            obstacle_collision_policy=ObstacleCollisionPolicy.PASS_THROUGH,
        )
        hit_box_repo.save(hit_box)

        service.tick() # 4サブステップ実行

        events = event_publisher.get_published_events()
        collision_events = [e for e in events if isinstance(e, HitBoxObstacleCollidedEvent)]
        # 壁に到達したタイミングで1度だけ発行されるべき
        assert len(collision_events) == 1

    def test_substep_negative_count_clamped_to_one(self, setup_service):
        """サブステップ数に負の値が指定されても 1 として扱われること"""
        config = DefaultHitBoxConfigService(substeps_per_tick=-5)
        assert config.get_substeps_per_tick() == 1

    def test_uses_adaptive_substeps_per_hit_box(self, setup_service):
        """HitBoxごとに設定サービス経由でサブステップ数を取得すること"""
        service, _, map_repo, _, _, hit_box_repo, _, _, _, _ = setup_service

        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(0, 0), TerrainType.grass()), Tile(Coordinate(0, 1), TerrainType.grass())]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        physical_map.add_object(WorldObject(
            WorldObjectId(100), Coordinate(0, 1), ObjectTypeEnum.PLAYER,
            component=ActorComponent(player_id=PlayerId(100)),
        ))
        owner_id = WorldObjectId(960)
        physical_map.add_object(WorldObject(owner_id, Coordinate(0, 0), ObjectTypeEnum.NPC, component=AutonomousBehaviorComponent()))
        map_repo.save(physical_map)

        hit_box = HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(7),
            spot_id=spot_id,
            owner_id=owner_id,
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0, 0, 0),
            start_tick=WorldTick(10),
            duration=10,
            velocity=HitBoxVelocity(1.0, 0.0, 0.0),
        )
        hit_box_repo.save(hit_box)

        import unittest.mock as mock
        with mock.patch.object(service._hit_box_config_service, "get_substeps_for_hit_box", return_value=6) as mocked:
            service.tick()
            assert mocked.call_count >= 1

    def test_hit_box_get_aggregated_events_deduplicates_same_payload(self):
        """同一内容のHitBoxイベントが重複した場合に集約されること（ドメイン層での検証）"""
        hit_box_id = HitBoxId.create(1)
        
        # HitBoxを最小限のパラメータで作成
        hit_box = HitBoxAggregate.create(
            hit_box_id=hit_box_id,
            spot_id=SpotId(1),
            owner_id=WorldObjectId(99),
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0, 0, 0),
            start_tick=WorldTick(0),
            duration=10,
        )
        hit_box.clear_events()

        moved_a = HitBoxMovedEvent.create(
            aggregate_id=hit_box_id,
            aggregate_type="HitBoxAggregate",
            from_coordinate=Coordinate(0, 0, 0),
            to_coordinate=Coordinate(1, 0, 0),
        )
        moved_b = HitBoxMovedEvent.create(
            aggregate_id=hit_box_id,
            aggregate_type="HitBoxAggregate",
            from_coordinate=Coordinate(0, 0, 0),
            to_coordinate=Coordinate(1, 0, 0),
        )
        
        # 直接イベントを追加（本来は内部メソッド経由だが集約ロジックのテストのため）
        hit_box.add_event(moved_a)
        hit_box.add_event(moved_b)

        aggregated = hit_box.get_aggregated_events()
        assert len(aggregated) == 1

    def test_collision_check_guard_limits_checks_and_continues(self, setup_service, caplog):
        """衝突判定上限に達した場合、警告を出して処理継続すること"""
        service, _, map_repo, _, _, hit_box_repo, _, _, _, _ = setup_service

        service._hit_box_config_service = DefaultHitBoxConfigService(
            substeps_per_tick=4,
            max_collision_checks_per_tick=1,
        )

        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(x, 0), TerrainType.grass()) for x in range(3)]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        physical_map.add_object(WorldObject(
            WorldObjectId(100), Coordinate(2, 0), ObjectTypeEnum.PLAYER,
            component=ActorComponent(player_id=PlayerId(100)),
        ))
        owner_id = WorldObjectId(970)
        target_id = WorldObjectId(971)
        physical_map.add_object(WorldObject(owner_id, Coordinate(0, 0), ObjectTypeEnum.NPC, component=AutonomousBehaviorComponent()))
        physical_map.add_object(WorldObject(target_id, Coordinate(1, 0), ObjectTypeEnum.NPC, component=AutonomousBehaviorComponent()))
        map_repo.save(physical_map)

        hit_box = HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(8),
            spot_id=spot_id,
            owner_id=owner_id,
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0, 0, 0),
            start_tick=WorldTick(10),
            duration=10,
            velocity=HitBoxVelocity(2.0, 0.0, 0.0),
            obstacle_collision_policy=ObstacleCollisionPolicy.PASS_THROUGH,
        )
        hit_box_repo.save(hit_box)

        caplog.set_level("WARNING")
        service.tick()

        assert any("Collision check guard triggered" in rec.message for rec in caplog.records)
        updated = hit_box_repo.find_by_id(HitBoxId.create(8))
        assert updated is not None

    def test_hit_box_stats_log_is_emitted(self, setup_service, caplog):
        """HitBox更新統計ログが出力されること"""
        service, _, map_repo, _, _, hit_box_repo, _, _, _, _ = setup_service
        caplog.set_level("DEBUG")

        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(0, 0), TerrainType.grass()), Tile(Coordinate(0, 1), TerrainType.grass())]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        physical_map.add_object(WorldObject(
            WorldObjectId(100), Coordinate(0, 1), ObjectTypeEnum.PLAYER,
            component=ActorComponent(player_id=PlayerId(100)),
        ))
        owner_id = WorldObjectId(980)
        physical_map.add_object(WorldObject(owner_id, Coordinate(0, 0), ObjectTypeEnum.NPC, component=AutonomousBehaviorComponent()))
        map_repo.save(physical_map)

        hit_box = HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(9),
            spot_id=spot_id,
            owner_id=owner_id,
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0, 0, 0),
            start_tick=WorldTick(10),
            duration=10,
            velocity=HitBoxVelocity(0.0, 0.0, 0.0),
        )
        hit_box_repo.save(hit_box)

        service.tick()
        assert any("HitBox update stats map=" in rec.message for rec in caplog.records)

    def test_tick_skips_hitbox_before_activation_tick(self, setup_service):
        """有効化時刻前のHitBoxはtickで移動も衝突判定も行われないこと"""
        service, _, map_repo, _, _, hit_box_repo, _, _, _, _ = setup_service

        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(x, 0), TerrainType.grass()) for x in range(3)]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        physical_map.add_object(WorldObject(
            WorldObjectId(100), Coordinate(2, 0), ObjectTypeEnum.PLAYER,
            component=ActorComponent(player_id=PlayerId(100)),
        ))
        map_repo.save(physical_map)

        hit_box = HitBoxAggregate.create(
            hit_box_id=HitBoxId.create(10),
            spot_id=spot_id,
            owner_id=WorldObjectId(990),
            shape=HitBoxShape.single_cell(),
            initial_coordinate=Coordinate(0, 0, 0),
            start_tick=WorldTick(10),
            duration=10,
            velocity=HitBoxVelocity(1, 0, 0),
            activation_tick=15, # Tick 15まで有効化されない
        )
        hit_box_repo.save(hit_box)

        # Tick 11 で実行
        service.tick() 

        updated = hit_box_repo.find_by_id(HitBoxId.create(10))
        # まだ移動していないはず
        assert updated.current_coordinate == Coordinate(0, 0, 0)

    def test_tick_executes_monster_skill(self, setup_service):
        """tickによってモンスターがスキルを使用し、HitBoxが生成されること"""
        service, _, repository, _, _, hit_box_repo, _, _, monster_repo, skill_loadout_repo = setup_service
        
        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(10) for y in range(10)]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        
        monster_obj_id = WorldObjectId(100)
        skills = [MonsterSkillInfo(slot_index=0, range=2, mp_cost=10)]
        monster_comp = AutonomousBehaviorComponent(
            state=BehaviorStateEnum.CHASE,
            vision_range=5,
            available_skills=skills,
            fov_angle=360.0,
        )
        monster_comp.target_id = WorldObjectId(1)
        monster_comp.last_known_target_position = Coordinate(7, 5)
        monster_obj = WorldObject(monster_obj_id, Coordinate(5, 5), ObjectTypeEnum.NPC, component=monster_comp)
        physical_map.add_object(monster_obj)
        
        player_wo_id = WorldObjectId(1)
        player_obj = WorldObject(
            player_wo_id,
            Coordinate(7, 5),
            ObjectTypeEnum.PLAYER,
            component=ActorComponent(player_id=PlayerId(100), race="human", faction="player"),
        )
        physical_map.add_object(player_obj)
        
        repository.save(physical_map)
        
        # モンスター集約を準備（スキル装備・スポーン済み）
        template = MonsterTemplate(
            template_id=MonsterTemplateId(1),
            name="test",
            base_stats=BaseStats(100, 100, 10, 10, 10, 0.05, 0.05),
            reward_info=RewardInfo(10, 10, "loot"),
            respawn_info=RespawnInfo(100, True),
            race=Race.HUMAN,
            faction=MonsterFactionEnum.ENEMY,
            description="Test monster",
            skill_ids=[SkillId(1)],
        )
        skill_spec = SkillSpec(
            skill_id=SkillId(1),
            name="s1",
            element=Element.NEUTRAL,
            deck_cost=1,
            cast_lock_ticks=1,
            cooldown_ticks=5,
            power_multiplier=1.0,
            hit_pattern=SkillHitPattern.single_pulse(SkillHitPatternType.MELEE, HitBoxShape.single_cell()),
            mp_cost=10,
        )
        loadout = SkillLoadoutAggregate.create(SkillLoadoutId(500), monster_obj_id.value, 10, 10)
        loadout.equip_skill(DeckTier.NORMAL, 0, skill_spec)
        skill_loadout_repo.save(loadout)
        
        monster = MonsterAggregate.create(MonsterId(1), template, monster_obj_id, skill_loadout=loadout)
        monster.spawn(Coordinate(5, 5, 0), spot_id, WorldTick(0))
        monster_repo.save(monster)
        
        # plan_action が USE_SKILL を返すようにモック
        use_skill_action = BehaviorAction(
            action_type=BehaviorActionType.USE_SKILL,
            coordinate=None,
            skill_slot_index=0,
        )
        with mock.patch.object(service._behavior_service, "plan_action", return_value=use_skill_action):
            service.tick()
        
        # HitBox が 1 つ生成されていること
        active = hit_box_repo.find_active_by_spot_id(spot_id)
        assert len(active) == 1
        assert active[0].owner_id == monster_obj_id
        assert active[0].skill_id == "1"
        # モンスターの MP 消費
        updated_monster = monster_repo.find_by_world_object_id(monster_obj_id)
        assert updated_monster.mp.value == 90

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

    class TestSkillContextAndTargetContext:
        """skill_context / target_context の組み立てと plan_action への渡し（正常・境界）"""

        def test_plan_action_receives_skill_context_for_monster_with_usable_slots(self, setup_service):
            # Given: モンスターが存在し、available_skills のスロットが can_use_skill で使用可能（アクティブスポットのためプレイヤーを配置）
            service, _, repository, _, _, _, _, _, monster_repo, skill_loadout_repo = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)
            physical_map.add_object(WorldObject(
                WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(100)),
            ))
            actor_id = WorldObjectId(1)
            actor = WorldObject(
                actor_id,
                Coordinate(2, 2),
                ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(
                    available_skills=[MonsterSkillInfo(slot_index=0, range=3, mp_cost=10)],
                ),
            )
            physical_map.add_object(actor)
            repository.save(physical_map)

            loadout_id = SkillLoadoutId.create(1)
            loadout = SkillLoadoutAggregate.create(loadout_id, 1, 10, 10)
            skill_spec = SkillSpec(
                skill_id=SkillId(1),
                name="s1",
                element=Element.NEUTRAL,
                deck_cost=1,
                cast_lock_ticks=1,
                cooldown_ticks=5,
                power_multiplier=1.0,
                hit_pattern=SkillHitPattern.single_pulse(SkillHitPatternType.MELEE, HitBoxShape.single_cell()),
                mp_cost=10,
            )
            loadout.equip_skill(DeckTier.NORMAL, 0, skill_spec)
            skill_loadout_repo.save(loadout)

            from ai_rpg_world.domain.monster.value_object.monster_template import MonsterTemplate
            from ai_rpg_world.domain.monster.value_object.monster_template_id import MonsterTemplateId
            from ai_rpg_world.domain.monster.value_object.respawn_info import RespawnInfo
            from ai_rpg_world.domain.monster.value_object.reward_info import RewardInfo
            template = MonsterTemplate(
                template_id=MonsterTemplateId(1),
                name="Test",
                base_stats=BaseStats(100, 100, 10, 10, 10, 0.05, 0.05),
                reward_info=RewardInfo(0, 0),
                respawn_info=RespawnInfo(1, True),
                race=Race.HUMAN,
                faction=MonsterFactionEnum.ENEMY,
                description="Test monster",
                skill_ids=[SkillId(1)],
            )
            monster = MonsterAggregate.create(
                MonsterId(1), template, WorldObjectId(1), skill_loadout=loadout
            )
            monster.spawn(Coordinate(2, 2, 0), spot_id, WorldTick(0))
            monster_repo.save(monster)

            captured = []
            def capture_plan_action(actor_id_arg, map_agg, **kwargs):
                captured.append(kwargs)
                return BehaviorAction.move(Coordinate(2, 3))

            with mock.patch.object(service._behavior_service, "plan_action", side_effect=capture_plan_action):
                service.tick()

            assert len(captured) == 2
            monster_captured = next(c for c in captured if c.get("skill_context") is not None)
            ctx = monster_captured["skill_context"]
            assert isinstance(ctx, SkillSelectionContext)
            assert 0 in ctx.usable_slot_indices

        def test_plan_action_receives_none_skill_context_for_non_autonomous_actor(self, setup_service):
            # Given: プレイヤー（ActorComponent）のみのマップ
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)
            player_id = PlayerId(100)
            actor = WorldObject(
                WorldObjectId(100),
                Coordinate(0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=player_id),
            )
            physical_map.add_object(actor)
            repository.save(physical_map)

            captured = []
            def capture_plan_action(actor_id_arg, map_agg, **kwargs):
                captured.append(kwargs)
                return BehaviorAction.wait()

            with mock.patch.object(service._behavior_service, "plan_action", side_effect=capture_plan_action):
                service.tick()

            assert len(captured) == 1
            assert captured[0].get("skill_context") is None

        def test_plan_action_receives_target_context_when_aggro_store_has_data(self, setup_service):
            # Given: aggro_store を注入し、該当アクターのヘイトデータを事前に登録（アクティブスポットのためプレイヤーを配置）
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            aggro_store = InMemoryAggroStore()
            aggro_store.add_aggro(SpotId(1), WorldObjectId(200), WorldObjectId(1), 5)
            service._aggro_store = aggro_store

            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)
            physical_map.add_object(WorldObject(
                WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(100)),
            ))
            actor_id = WorldObjectId(1)
            actor = WorldObject(
                actor_id,
                Coordinate(2, 2),
                ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(),
            )
            physical_map.add_object(actor)
            repository.save(physical_map)

            captured = []
            def capture_plan_action(actor_id_arg, map_agg, **kwargs):
                captured.append(kwargs)
                return BehaviorAction.move(Coordinate(2, 3))

            with mock.patch.object(service._behavior_service, "plan_action", side_effect=capture_plan_action):
                service.tick()

            assert len(captured) == 2
            npc_captured = next(c for c in captured if c.get("target_context") is not None)
            ctx = npc_captured["target_context"]
            assert isinstance(ctx, TargetSelectionContext)
            assert ctx.threat_by_id == {WorldObjectId(200): 5}

        def test_plan_action_receives_none_target_context_when_aggro_store_not_injected(self, setup_service):
            # Given: aggro_store は None（デフォルト）。アクティブスポットのためプレイヤーを配置
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            assert service._aggro_store is None

            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)
            physical_map.add_object(WorldObject(
                WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(100)),
            ))
            actor = WorldObject(
                WorldObjectId(1),
                Coordinate(2, 2),
                ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(),
            )
            physical_map.add_object(actor)
            repository.save(physical_map)

            captured = []
            def capture_plan_action(actor_id_arg, map_agg, **kwargs):
                captured.append(kwargs)
                return BehaviorAction.move(Coordinate(2, 3))

            with mock.patch.object(service._behavior_service, "plan_action", side_effect=capture_plan_action):
                service.tick()

            assert len(captured) == 2
            assert all(c.get("target_context") is None for c in captured)

        def test_plan_action_receives_target_context_with_memory_policy_forgotten_excluded(self, setup_service):
            """aggro_memory_policy で忘却済みのヘイトは target_context に含まれないこと（last_seen から経過で忘却）"""
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            aggro_store = InMemoryAggroStore()
            aggro_store.add_aggro(SpotId(1), WorldObjectId(200), WorldObjectId(1), 5, current_tick=0)
            service._aggro_store = aggro_store
            service._time_provider = InMemoryGameTimeProvider(initial_tick=20)

            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)
            physical_map.add_object(WorldObject(
                WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(100)),
            ))
            actor_id = WorldObjectId(1)
            actor = WorldObject(
                actor_id,
                Coordinate(2, 2),
                ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(
                    aggro_memory_policy=AggroMemoryPolicy(forget_after_ticks=10),
                ),
            )
            physical_map.add_object(actor)
            repository.save(physical_map)

            captured = []
            def capture_plan_action(actor_id_arg, map_agg, **kwargs):
                captured.append(kwargs)
                return BehaviorAction.wait()

            with mock.patch.object(service._behavior_service, "plan_action", side_effect=capture_plan_action):
                service.tick()

            assert service._time_provider.get_current_tick().value == 21
            for c in captured:
                ctx = c.get("target_context")
                assert ctx is None or ctx.threat_by_id == {}, "忘却済みのヘイトは target_context に含まれないこと"

    class TestGrowthContext:
        """_build_growth_context_for_actor の組み立て（正常・境界・例外）"""

        def test_build_growth_context_returns_none_for_non_autonomous_actor(self, setup_service):
            """自律行動コンポーネントでないアクター（プレイヤー等）の場合は None を返すこと"""
            service, _, _, _, _, _, _, _, _, _ = setup_service
            player_actor = WorldObject(
                WorldObjectId(100),
                Coordinate(0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(100)),
            )
            result = service._build_growth_context_for_actor(player_actor, WorldTick(0))
            assert result is None

        def test_build_growth_context_returns_none_when_monster_not_found(self, setup_service):
            """モンスターリポジトリに該当 world_object_id のモンスターが存在しない場合は None を返すこと"""
            service, _, repository, _, _, _, _, _, monster_repo, _ = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(3) for y in range(3)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)
            actor_id = WorldObjectId(999)
            physical_map.add_object(WorldObject(
                actor_id,
                Coordinate(1, 1),
                ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(),
            ))
            repository.save(physical_map)
            # monster_repo には 999 を world_object_id に持つモンスターを登録していない
            result = service._build_growth_context_for_actor(
                physical_map.get_object(actor_id), WorldTick(0)
            )
            assert result is None

        def test_build_growth_context_returns_none_when_monster_has_no_growth_stages(self, setup_service):
            """モンスターのテンプレートに growth_stages が無い（空）場合は None を返すこと"""
            service, _, repository, _, _, _, _, _, monster_repo, skill_loadout_repo = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(3) for y in range(3)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)
            physical_map.add_object(WorldObject(
                WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(100)),
            ))
            actor_id = WorldObjectId(1)
            physical_map.add_object(WorldObject(
                actor_id, Coordinate(1, 1), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(),
            ))
            repository.save(physical_map)

            template = MonsterTemplate(
                template_id=MonsterTemplateId(1),
                name="NoGrowth",
                base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
                reward_info=RewardInfo(0, 0),
                respawn_info=RespawnInfo(1, True),
                race=Race.HUMAN,
                faction=MonsterFactionEnum.ENEMY,
                description="No growth stages",
                skill_ids=[],
            )
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), 1, 10, 10)
            monster = MonsterAggregate.create(MonsterId(1), template, actor_id, skill_loadout=loadout)
            monster.spawn(Coordinate(1, 1, 0), spot_id, WorldTick(0))
            monster_repo.save(monster)

            result = service._build_growth_context_for_actor(
                physical_map.get_object(actor_id), WorldTick(0)
            )
            assert result is None

        def test_build_growth_context_returns_context_when_monster_has_growth_stages(self, setup_service):
            """モンスターのテンプレートに growth_stages がある場合は GrowthContext を返すこと"""
            from ai_rpg_world.domain.monster.value_object.growth_stage import GrowthStage
            service, _, repository, _, _, _, _, _, monster_repo, skill_loadout_repo = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(3) for y in range(3)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)
            physical_map.add_object(WorldObject(
                WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(100)),
            ))
            actor_id = WorldObjectId(1)
            physical_map.add_object(WorldObject(
                actor_id, Coordinate(1, 1), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(),
            ))
            repository.save(physical_map)

            template = MonsterTemplate(
                template_id=MonsterTemplateId(2),
                name="WithGrowth",
                base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
                reward_info=RewardInfo(0, 0),
                respawn_info=RespawnInfo(1, True),
                race=Race.HUMAN,
                faction=MonsterFactionEnum.ENEMY,
                description="Has growth stages",
                skill_ids=[],
                growth_stages=[
                    GrowthStage(after_ticks=0, stats_multiplier=0.8, flee_bias_multiplier=1.5, allow_chase=False),
                    GrowthStage(after_ticks=100, stats_multiplier=1.0),
                ],
            )
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(2), 1, 10, 10)
            monster = MonsterAggregate.create(MonsterId(2), template, actor_id, skill_loadout=loadout)
            monster.spawn(Coordinate(1, 1, 0), spot_id, WorldTick(0))
            monster_repo.save(monster)

            result = service._build_growth_context_for_actor(
                physical_map.get_object(actor_id), WorldTick(50)
            )
            assert result is not None
            assert isinstance(result, GrowthContext)
            assert result.effective_flee_threshold == 0.3  # 0.2 * 1.5 = 0.3, min(1.0, 0.3)
            assert result.allow_chase is False

    class TestActorExecutionOrder:
        """実行順ソート（同一スポット内でプレイヤーとの距離順）の正常・境界・異常系"""

        def test_actors_processed_in_order_of_distance_to_player_when_player_on_map(self, setup_service):
            """同一マップにプレイヤーがいる場合、プレイヤーに近いアクターから順に plan_action が呼ばれること"""
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(10) for y in range(10)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)

            player_id = PlayerId(100)
            player_coord = Coordinate(0, 0)
            physical_map.add_object(WorldObject(
                WorldObjectId(100),
                player_coord,
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=player_id),
            ))

            near_id = WorldObjectId(1)
            mid_id = WorldObjectId(2)
            far_id = WorldObjectId(3)
            physical_map.add_object(WorldObject(
                near_id, Coordinate(1, 0), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(state=BehaviorStateEnum.PATROL, patrol_points=[Coordinate(1, 0), Coordinate(1, 1)]),
            ))
            physical_map.add_object(WorldObject(
                mid_id, Coordinate(3, 0), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(state=BehaviorStateEnum.PATROL, patrol_points=[Coordinate(3, 0), Coordinate(3, 1)]),
            ))
            physical_map.add_object(WorldObject(
                far_id, Coordinate(5, 0), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(state=BehaviorStateEnum.PATROL, patrol_points=[Coordinate(5, 0), Coordinate(5, 1)]),
            ))
            repository.save(physical_map)

            call_order = []
            def capture_order(actor_id_arg, map_agg, **kwargs):
                call_order.append(actor_id_arg)
                return BehaviorAction.move(Coordinate(0, 0))

            with mock.patch.object(service._behavior_service, "plan_action", side_effect=capture_order):
                service.tick()

            assert len(call_order) == 4
            assert call_order[0] == WorldObjectId(100)
            assert call_order[1] == near_id
            assert call_order[2] == mid_id
            assert call_order[3] == far_id

        def test_actors_processed_when_no_player_on_map(self, setup_service):
            """同一マップにプレイヤーがいない場合、そのスポットは凍結され plan_action は呼ばれないこと"""
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)

            for i, coord in enumerate([Coordinate(1, 1), Coordinate(2, 2), Coordinate(3, 3)]):
                actor_id = WorldObjectId(10 + i)
                physical_map.add_object(WorldObject(
                    actor_id, coord, ObjectTypeEnum.NPC,
                    component=AutonomousBehaviorComponent(state=BehaviorStateEnum.PATROL, patrol_points=[coord, coord]),
                ))
            repository.save(physical_map)

            call_count = [0]
            def count_calls(actor_id_arg, map_agg, **kwargs):
                call_count[0] += 1
                return BehaviorAction.move(Coordinate(0, 0))

            with mock.patch.object(service._behavior_service, "plan_action", side_effect=count_calls):
                service.tick()

            assert call_count[0] == 0

        def test_actors_sorted_by_nearest_player_when_multiple_players(self, setup_service):
            """同一マップに複数プレイヤーがいる場合、最も近いプレイヤーとの距離でソートされること"""
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(15) for y in range(5)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)

            physical_map.add_object(WorldObject(
                WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(100)),
            ))
            physical_map.add_object(WorldObject(
                WorldObjectId(101), Coordinate(10, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(101)),
            ))

            near_p1_id = WorldObjectId(1)
            mid_id = WorldObjectId(2)
            near_p2_id = WorldObjectId(3)
            physical_map.add_object(WorldObject(
                near_p1_id, Coordinate(1, 0), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(state=BehaviorStateEnum.PATROL, patrol_points=[Coordinate(1, 0), Coordinate(1, 1)]),
            ))
            physical_map.add_object(WorldObject(
                mid_id, Coordinate(5, 0), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(state=BehaviorStateEnum.PATROL, patrol_points=[Coordinate(5, 0), Coordinate(5, 1)]),
            ))
            physical_map.add_object(WorldObject(
                near_p2_id, Coordinate(9, 0), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(state=BehaviorStateEnum.PATROL, patrol_points=[Coordinate(9, 0), Coordinate(9, 1)]),
            ))
            repository.save(physical_map)

            call_order = []
            def capture_order(actor_id_arg, map_agg, **kwargs):
                call_order.append(actor_id_arg)
                return BehaviorAction.move(Coordinate(0, 0))

            with mock.patch.object(service._behavior_service, "plan_action", side_effect=capture_order):
                service.tick()

            assert len(call_order) == 5
            npc_order = [oid for oid in call_order if oid in (near_p1_id, mid_id, near_p2_id)]
            assert npc_order[0] == near_p1_id
            assert npc_order[1] == near_p2_id
            assert npc_order[2] == mid_id

        def test_single_actor_no_player_on_map(self, setup_service):
            """プレイヤーがいないマップではスポットが凍結され plan_action は呼ばれないこと"""
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)
            actor_id = WorldObjectId(1)
            physical_map.add_object(WorldObject(
                actor_id, Coordinate(2, 2), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(state=BehaviorStateEnum.PATROL, patrol_points=[Coordinate(2, 2), Coordinate(2, 3)]),
            ))
            repository.save(physical_map)

            call_count = [0]
            def count_calls(actor_id_arg, map_agg, **kwargs):
                call_count[0] += 1
                return BehaviorAction.move(Coordinate(2, 3))

            with mock.patch.object(service._behavior_service, "plan_action", side_effect=count_calls):
                service.tick()

            assert call_count[0] == 0

        def test_busy_actors_skipped_regardless_of_execution_order(self, setup_service):
            """実行順ソート後も、Busy なアクターは plan_action が呼ばれずスキップされること"""
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)

            player_id = PlayerId(100)
            physical_map.add_object(WorldObject(
                WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=player_id),
            ))
            near_id = WorldObjectId(1)
            far_busy_id = WorldObjectId(2)
            physical_map.add_object(WorldObject(
                near_id, Coordinate(1, 0), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(state=BehaviorStateEnum.PATROL, patrol_points=[Coordinate(1, 0), Coordinate(1, 1)]),
            ))
            physical_map.add_object(WorldObject(
                far_busy_id, Coordinate(3, 0), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(state=BehaviorStateEnum.PATROL, patrol_points=[Coordinate(3, 0), Coordinate(3, 1)]),
                busy_until=WorldTick(999),
            ))
            repository.save(physical_map)

            called_ids = []
            def capture_called(actor_id_arg, map_agg, **kwargs):
                called_ids.append(actor_id_arg)
                return BehaviorAction.wait()

            with mock.patch.object(service._behavior_service, "plan_action", side_effect=capture_called):
                service.tick()

            assert near_id in called_ids
            assert WorldObjectId(100) in called_ids
            assert far_busy_id not in called_ids

        def test_empty_actors_no_crash(self, setup_service):
            """アクターが0体のマップ（プレイヤーもいない）でも plan_action が呼ばれず正常終了すること"""
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(3) for y in range(3)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)
            repository.save(physical_map)

            call_count = [0]
            def count_calls(actor_id_arg, map_agg, **kwargs):
                call_count[0] += 1
                return BehaviorAction.wait()

            with mock.patch.object(service._behavior_service, "plan_action", side_effect=count_calls):
                service.tick()

            assert call_count[0] == 0

        def test_player_only_map_execution_order(self, setup_service):
            """プレイヤーのみがいるマップでは plan_action が1回だけ呼ばれること"""
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)
            player_id = PlayerId(100)
            physical_map.add_object(WorldObject(
                WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=player_id),
            ))
            repository.save(physical_map)

            call_order = []
            def capture_order(actor_id_arg, map_agg, **kwargs):
                call_order.append(actor_id_arg)
                return BehaviorAction.wait()

            with mock.patch.object(service._behavior_service, "plan_action", side_effect=capture_order):
                service.tick()

            assert len(call_order) == 1
            assert call_order[0] == WorldObjectId(100)

    class TestActiveSpotFreeze:
        """スポット単位凍結（プレイヤーが存在するマップでのみ逐次更新）の正常・境界・異常系"""

        def test_only_active_spot_gets_plan_action_and_save(self, setup_service):
            """プレイヤーがいるスポットのみ plan_action が呼ばれ、そのスポットのみ save されること"""
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            spot_a = SpotId(1)
            spot_b = SpotId(2)
            tiles_5x5 = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
            map_a = PhysicalMapAggregate.create(spot_a, tiles_5x5)
            map_b = PhysicalMapAggregate.create(spot_b, tiles_5x5)
            player_id = PlayerId(100)
            map_a.add_object(WorldObject(
                WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=player_id),
            ))
            map_a.add_object(WorldObject(
                WorldObjectId(1), Coordinate(1, 1), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(state=BehaviorStateEnum.PATROL, patrol_points=[Coordinate(1, 1), Coordinate(1, 2)]),
            ))
            map_b.add_object(WorldObject(
                WorldObjectId(2), Coordinate(2, 2), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(state=BehaviorStateEnum.PATROL, patrol_points=[Coordinate(2, 2), Coordinate(2, 3)]),
            ))
            repository.save(map_a)
            repository.save(map_b)

            plan_action_calls = []
            def capture_plan(actor_id_arg, map_agg, **kwargs):
                plan_action_calls.append((actor_id_arg, map_agg.spot_id))
                return BehaviorAction.wait()

            save_calls = []
            original_save = repository.save
            def capture_save(physical_map):
                save_calls.append(physical_map.spot_id)
                return original_save(physical_map)

            with mock.patch.object(service._behavior_service, "plan_action", side_effect=capture_plan):
                with mock.patch.object(service._physical_map_repository, "save", side_effect=capture_save):
                    service.tick()

            assert all(spot_id == spot_a for _, spot_id in plan_action_calls)
            assert len(plan_action_calls) == 2
            assert save_calls == [spot_a]

        def test_no_player_on_any_map_no_plan_action_no_save(self, setup_service):
            """全マップにプレイヤーがいない場合、plan_action も save も呼ばれないこと"""
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            spot_a = SpotId(10)
            spot_b = SpotId(20)
            tiles = [Tile(Coordinate(0, 0), TerrainType.grass())]
            map_a = PhysicalMapAggregate.create(spot_a, tiles)
            map_b = PhysicalMapAggregate.create(spot_b, tiles)
            map_a.add_object(WorldObject(
                WorldObjectId(1), Coordinate(0, 0), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(state=BehaviorStateEnum.PATROL, patrol_points=[Coordinate(0, 0)]),
            ))
            map_b.add_object(WorldObject(
                WorldObjectId(2), Coordinate(0, 0), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(state=BehaviorStateEnum.PATROL, patrol_points=[Coordinate(0, 0)]),
            ))
            repository.save(map_a)
            repository.save(map_b)

            plan_count = [0]
            save_count = [0]
            def count_plan(*args, **kwargs):
                plan_count[0] += 1
                return BehaviorAction.wait()
            original_save = repository.save
            def count_save(physical_map):
                save_count[0] += 1
                return original_save(physical_map)

            with mock.patch.object(service._behavior_service, "plan_action", side_effect=count_plan):
                with mock.patch.object(service._physical_map_repository, "save", side_effect=count_save):
                    service.tick()

            assert plan_count[0] == 0
            assert save_count[0] == 0

        def test_both_spots_with_players_both_updated(self, setup_service):
            """複数スポットにそれぞれプレイヤーがいる場合、両方のスポットで plan_action と save が行われること"""
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            spot_a = SpotId(1)
            spot_b = SpotId(2)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(3) for y in range(3)]
            map_a = PhysicalMapAggregate.create(spot_a, tiles)
            map_b = PhysicalMapAggregate.create(spot_b, tiles)
            map_a.add_object(WorldObject(
                WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(100)),
            ))
            map_b.add_object(WorldObject(
                WorldObjectId(101), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(101)),
            ))
            repository.save(map_a)
            repository.save(map_b)

            plan_spot_ids = []
            def capture_spot(actor_id_arg, map_agg, **kwargs):
                plan_spot_ids.append(map_agg.spot_id)
                return BehaviorAction.wait()

            save_spot_ids = []
            original_save = repository.save
            def capture_save(physical_map):
                save_spot_ids.append(physical_map.spot_id)
                return original_save(physical_map)

            with mock.patch.object(service._behavior_service, "plan_action", side_effect=capture_spot):
                with mock.patch.object(service._physical_map_repository, "save", side_effect=capture_save):
                    service.tick()

            assert set(plan_spot_ids) == {spot_a, spot_b}
            assert set(save_spot_ids) == {spot_a, spot_b}

        def test_inactive_spot_actors_never_get_plan_action(self, setup_service):
            """プレイヤーがいないスポットのアクターには plan_action が一度も呼ばれないこと"""
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            spot_active = SpotId(1)
            spot_inactive = SpotId(2)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
            map_active = PhysicalMapAggregate.create(spot_active, tiles)
            map_inactive = PhysicalMapAggregate.create(spot_inactive, tiles)
            map_active.add_object(WorldObject(
                WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(100)),
            ))
            map_active.add_object(WorldObject(
                WorldObjectId(1), Coordinate(1, 0), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(state=BehaviorStateEnum.PATROL, patrol_points=[Coordinate(1, 0), Coordinate(1, 1)]),
            ))
            npc_on_inactive_id = WorldObjectId(2)
            map_inactive.add_object(WorldObject(
                npc_on_inactive_id, Coordinate(2, 2), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(state=BehaviorStateEnum.PATROL, patrol_points=[Coordinate(2, 2), Coordinate(2, 3)]),
            ))
            repository.save(map_active)
            repository.save(map_inactive)

            plan_actor_ids = []
            def capture_actor(actor_id_arg, map_agg, **kwargs):
                plan_actor_ids.append(actor_id_arg)
                return BehaviorAction.wait()

            with mock.patch.object(service._behavior_service, "plan_action", side_effect=capture_actor):
                service.tick()

            assert npc_on_inactive_id not in plan_actor_ids
            assert WorldObjectId(100) in plan_actor_ids
            assert WorldObjectId(1) in plan_actor_ids

        def test_single_map_with_player_behaves_as_before(self, setup_service):
            """プレイヤーが1人いるマップが1つの場合は従来どおり更新され、tick が正常終了すること"""
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)
            player_id_wo = WorldObjectId(100)
            actor_id = WorldObjectId(1)
            physical_map.add_object(WorldObject(
                player_id_wo, Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(100)),
            ))
            physical_map.add_object(WorldObject(
                actor_id, Coordinate(2, 2), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(state=BehaviorStateEnum.PATROL, patrol_points=[Coordinate(2, 2), Coordinate(2, 3)]),
            ))
            repository.save(physical_map)

            def plan_by_actor(actor_id_arg, map_agg, **kwargs):
                if actor_id_arg == player_id_wo:
                    return BehaviorAction.wait()
                return BehaviorAction.move(Coordinate(2, 3))

            with mock.patch.object(service._behavior_service, "plan_action", side_effect=plan_by_actor):
                service.tick()

            updated = repository.find_by_spot_id(spot_id)
            assert updated.get_object(actor_id).coordinate == Coordinate(2, 3)

        def test_active_spot_save_called_once_per_active_map(self, setup_service):
            """アクティブなスポットごとに save が1回だけ呼ばれること（境界）"""
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(0, 0), TerrainType.grass())]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)
            physical_map.add_object(WorldObject(
                WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(100)),
            ))
            repository.save(physical_map)

            save_count = [0]
            original_save = repository.save
            def count_save(physical_map):
                save_count[0] += 1
                return original_save(physical_map)

            with mock.patch.object(service._physical_map_repository, "save", side_effect=count_save):
                service.tick()

            assert save_count[0] == 1

    class TestActiveTimeSkip:
        """活動時間帯でない自律アクターは plan_action をスキップするテスト"""

        def test_nocturnal_actor_skipped_during_day(self, setup_service):
            """昼の時間帯では夜行性アクターは plan_action を呼ばれないこと"""
            service, time_provider, repository, _, _, _, _, _, _, _ = setup_service
            # ticks_per_day=24 で initial_tick=12 → advance で 13 → DAY
            time_provider.advance_tick()
            time_provider.advance_tick()
            time_provider.advance_tick()
            # 現在 13 (DAY)
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)
            physical_map.add_object(WorldObject(
                WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(100)),
            ))
            nocturnal_id = WorldObjectId(1)
            physical_map.add_object(WorldObject(
                nocturnal_id,
                Coordinate(2, 2),
                ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(
                    state=BehaviorStateEnum.PATROL,
                    patrol_points=[Coordinate(2, 2), Coordinate(2, 3)],
                    active_time=ActiveTimeType.NOCTURNAL,
                ),
            ))
            repository.save(physical_map)

            plan_actor_ids = []
            def capture_actor(actor_id_arg, map_agg, **kwargs):
                plan_actor_ids.append(actor_id_arg)
                return BehaviorAction.wait()

            with mock.patch.object(service._behavior_service, "plan_action", side_effect=capture_actor):
                service.tick()

            # プレイヤー(100)は ActorComponent のみなので plan_action は呼ばれる（自律でないのでスキップ判定は通る）
            # NOCTURNAL の NPC(1) は活動時間でないので plan_action が呼ばれない
            assert nocturnal_id not in plan_actor_ids

        def test_diurnal_actor_acts_during_day(self, setup_service):
            """昼の時間帯では昼行性アクターは plan_action が呼ばれること"""
            service, time_provider, repository, _, _, _, _, _, _, _ = setup_service
            time_provider.advance_tick()
            time_provider.advance_tick()
            time_provider.advance_tick()
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)
            physical_map.add_object(WorldObject(
                WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(100)),
            ))
            diurnal_id = WorldObjectId(1)
            physical_map.add_object(WorldObject(
                diurnal_id,
                Coordinate(2, 2),
                ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(
                    state=BehaviorStateEnum.PATROL,
                    patrol_points=[Coordinate(2, 2), Coordinate(2, 3)],
                    active_time=ActiveTimeType.DIURNAL,
                ),
            ))
            repository.save(physical_map)

            plan_actor_ids = []
            def capture_actor(actor_id_arg, map_agg, **kwargs):
                plan_actor_ids.append(actor_id_arg)
                return BehaviorAction.wait()

            with mock.patch.object(service._behavior_service, "plan_action", side_effect=capture_actor):
                service.tick()

            assert diurnal_id in plan_actor_ids

    class TestRespawnLoop:
        """リスポーンループのテスト"""

        def test_dead_monster_respawns_when_interval_elapsed_and_condition_met(self, setup_service):
            """DEAD モンスターがリスポーン間隔経過かつ条件を満たすときリスポーンすること"""
            service, time_provider, repository, _, _, _, _, _, monster_repo, skill_loadout_repo = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)
            physical_map.add_object(WorldObject(
                WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(100)),
            ))
            repository.save(physical_map)

            monster_obj_id = WorldObjectId(1)
            respawn_interval = 50
            template = MonsterTemplate(
                template_id=MonsterTemplateId(1),
                name="test",
                base_stats=BaseStats(100, 100, 10, 10, 10, 0.05, 0.05),
                reward_info=RewardInfo(10, 10, "loot"),
                respawn_info=RespawnInfo(respawn_interval_ticks=respawn_interval, is_auto_respawn=True),
                race=Race.HUMAN,
                faction=MonsterFactionEnum.ENEMY,
                description="Test",
                skill_ids=[],
            )
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(500), monster_obj_id.value, 10, 10)
            skill_loadout_repo.save(loadout)
            monster = MonsterAggregate.create(MonsterId(1), template, monster_obj_id, skill_loadout=loadout)
            spawn_coord = Coordinate(2, 2, 0)
            monster.spawn(spawn_coord, spot_id, WorldTick(0))
            monster.apply_damage(100, WorldTick(100))
            monster_repo.save(monster)
            assert monster.status == MonsterStatusEnum.DEAD
            assert monster.spot_id == spot_id
            assert monster.get_respawn_coordinate() == spawn_coord

            # initial_tick=10 なので 10 回 advance すると 20。リスポーンは 100+50=150 なので届かない。
            # time_provider を 149 にしておき、1 tick で 150 にする
            for _ in range(139):
                time_provider.advance_tick()
            assert time_provider.get_current_tick().value == 149

            service.tick()

            updated = monster_repo.find_by_id(MonsterId(1))
            assert updated.status == MonsterStatusEnum.ALIVE
            assert updated.coordinate == spawn_coord
            assert updated.spot_id == spot_id
