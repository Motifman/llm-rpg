import pytest
from datetime import datetime
from typing import List, Dict
from unittest.mock import patch

from ai_rpg_world.application.world.services.movement_service import MovementApplicationService
from ai_rpg_world.application.world.services.movement_step_executor import MovementStepExecutor
from ai_rpg_world.application.world.services.set_destination_service import SetDestinationService
from ai_rpg_world.application.world.world_query_wiring import create_world_query_service
from ai_rpg_world.application.world.contracts.commands import (
    CancelMovementCommand,
    MoveTileCommand,
    SetDestinationCommand,
    TickMovementCommand,
)
from ai_rpg_world.application.world.contracts.queries import GetPlayerLocationQuery
from ai_rpg_world.domain.world.entity.location_area import LocationArea
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.domain.world.exception.map_exception import (
    LocationAreaNotFoundException,
    ObjectNotFoundException,
)
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    MovementCommandException,
    PlayerNotFoundException,
    MapNotFoundException,
    MovementInvalidException,
    PlayerStaminaExhaustedException,
    PathBlockedException,
    ActorBusyException,
)
from ai_rpg_world.application.world.exceptions.base_exception import WorldSystemErrorException
from ai_rpg_world.domain.common.exception import DomainException
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_navigation_state import PlayerNavigationState
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import PlayerProfileAggregate
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.enum.player_enum import Role
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.entity.gateway import Gateway
from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
from ai_rpg_world.domain.world.value_object.area import RectArea
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, DirectionEnum, EnvironmentTypeEnum
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent, ChestComponent
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.domain.world.service.map_transition_service import MapTransitionService
from ai_rpg_world.domain.world.service.global_pathfinding_service import GlobalPathfindingService
from ai_rpg_world.domain.world.service.movement_config_service import DefaultMovementConfigService
from ai_rpg_world.domain.player.event.status_events import PlayerLocationChangedEvent, PlayerStaminaConsumedEvent
from ai_rpg_world.domain.pursuit.value_object.pursuit_target_snapshot import PursuitTargetSnapshot
from ai_rpg_world.domain.world.event.map_events import WorldObjectMovedEvent, GatewayTriggeredEvent
from ai_rpg_world.application.world.handlers.gateway_handler import GatewayTriggeredEventHandler
from ai_rpg_world.infrastructure.events import EventHandlerComposition, EventHandlerProfile
from ai_rpg_world.infrastructure.world.pathfinding.astar_pathfinding_strategy import AStarPathfindingStrategy
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import InMemoryPlayerStatusRepository
from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import InMemoryPlayerProfileRepository
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import InMemoryPhysicalMapRepository
from ai_rpg_world.infrastructure.repository.in_memory_spot_repository import InMemorySpotRepository
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.application.world.services.gateway_based_connected_spots_provider import (
    GatewayBasedConnectedSpotsProvider,
)
from ai_rpg_world.application.world.services.transition_condition_evaluator import TransitionConditionEvaluator
from ai_rpg_world.domain.world.value_object.transition_condition import RequireToll, block_if_weather
from ai_rpg_world.infrastructure.repository.in_memory_transition_policy_repository import (
    InMemoryTransitionPolicyRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_monster_aggregate_repository import (
    InMemoryMonsterAggregateRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import InMemoryGameTimeProvider


class TestMovementApplicationService:
    @pytest.fixture
    def setup_service(self):
        data_store = InMemoryDataStore()
        data_store.clear_all()

        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow, data_store=data_store)

        unit_of_work, event_publisher = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow,
            data_store=data_store
        )
        
        player_status_repo = InMemoryPlayerStatusRepository(data_store, unit_of_work)
        player_profile_repo = InMemoryPlayerProfileRepository(data_store, unit_of_work)
        physical_map_repo = InMemoryPhysicalMapRepository(data_store, unit_of_work)
        spot_repo = InMemorySpotRepository(data_store, unit_of_work)
        connected_spots_provider = GatewayBasedConnectedSpotsProvider(physical_map_repo)
        monster_repo = InMemoryMonsterAggregateRepository(data_store, unit_of_work)

        pathfinding_service = PathfindingService(AStarPathfindingStrategy())
        global_pathfinding_service = GlobalPathfindingService(pathfinding_service)
        movement_config_service = DefaultMovementConfigService()
        map_transition_service = MapTransitionService()
        time_provider = InMemoryGameTimeProvider(initial_tick=100)

        # 同期イベントハンドラの登録（プロファイルで移動・ゲートウェイのみ）
        gateway_handler = GatewayTriggeredEventHandler(
            physical_map_repository=physical_map_repo,
            player_status_repository=player_status_repo,
            monster_repository=monster_repo,
            map_transition_service=map_transition_service,
            unit_of_work=unit_of_work,
            event_publisher=event_publisher,
        )
        composition = EventHandlerComposition(gateway_handler=gateway_handler)
        composition.register_for_profile(event_publisher, EventHandlerProfile.MOVEMENT_ONLY)

        set_destination_service = SetDestinationService(
            player_status_repository=player_status_repo,
            physical_map_repository=physical_map_repo,
            connected_spots_provider=connected_spots_provider,
            global_pathfinding_service=global_pathfinding_service,
        )
        movement_step_executor = MovementStepExecutor(
            player_status_repository=player_status_repo,
            player_profile_repository=player_profile_repo,
            physical_map_repository=physical_map_repo,
            spot_repository=spot_repo,
            movement_config_service=movement_config_service,
            time_provider=time_provider,
            unit_of_work=unit_of_work,
        )
        service = MovementApplicationService(
            set_destination_service=set_destination_service,
            movement_step_executor=movement_step_executor,
            player_status_repository=player_status_repo,
            player_profile_repository=player_profile_repo,
            physical_map_repository=physical_map_repo,
            spot_repository=spot_repo,
            connected_spots_provider=connected_spots_provider,
            global_pathfinding_service=global_pathfinding_service,
            movement_config_service=movement_config_service,
            time_provider=time_provider,
            unit_of_work=unit_of_work,
        )
        world_query_service = create_world_query_service(
            player_status_repository=player_status_repo,
            player_profile_repository=player_profile_repo,
            physical_map_repository=physical_map_repo,
            spot_repository=spot_repo,
            connected_spots_provider=connected_spots_provider,
        )

        # デフォルトのスポットを登録しておく
        spot_repo.save(Spot(SpotId(1), "Default Spot", ""))

        return service, world_query_service, player_status_repo, player_profile_repo, physical_map_repo, spot_repo, unit_of_work, time_provider, event_publisher

    @pytest.fixture
    def setup_service_with_transition_policy(self, setup_service):
        """遷移条件評価付きの MovementApplicationService を返す（Phase 6 用）"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, uow, time_provider, event_publisher = setup_service
        policy_repo = InMemoryTransitionPolicyRepository()
        evaluator = TransitionConditionEvaluator()
        set_destination_service = SetDestinationService(
            player_status_repository=status_repo,
            physical_map_repository=phys_repo,
            connected_spots_provider=service._connected_spots_provider,
            global_pathfinding_service=service._global_pathfinding_service,
        )
        movement_step_executor = MovementStepExecutor(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
            movement_config_service=service._movement_config_service,
            time_provider=time_provider,
            unit_of_work=uow,
            transition_policy_repository=policy_repo,
            transition_condition_evaluator=evaluator,
        )
        service_with_policy = MovementApplicationService(
            set_destination_service=set_destination_service,
            movement_step_executor=movement_step_executor,
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
            connected_spots_provider=service._connected_spots_provider,
            global_pathfinding_service=service._global_pathfinding_service,
            movement_config_service=service._movement_config_service,
            time_provider=time_provider,
            unit_of_work=uow,
        )
        return service_with_policy, status_repo, profile_repo, phys_repo, spot_repo, policy_repo, uow, time_provider, event_publisher

    def _create_sample_status(
        self,
        player_id: int,
        spot_id: int = 1,
        x: int = 0,
        y: int = 0,
        navigation_state: PlayerNavigationState | None = None,
    ):
        nav = navigation_state or PlayerNavigationState.from_parts(
            current_spot_id=SpotId(spot_id),
            current_coordinate=Coordinate(x, y, 0),
        )
        exp_table = ExpTable(100, 1.5)
        return PlayerStatusAggregate(
            player_id=PlayerId(player_id),
            base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
            stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
            exp_table=exp_table,
            growth=Growth(1, 0, exp_table),
            gold=Gold(1000),
            hp=Hp.create(100, 100),
            mp=Mp.create(50, 50),
            stamina=Stamina.create(100, 100),
            navigation_state=nav,
        )

    def _create_sample_profile(self, player_id: int, name: str = "TestPlayer"):
        return PlayerProfileAggregate.create(
            player_id=PlayerId(player_id),
            name=PlayerName(name),
            role=Role.CITIZEN
        )

    def _create_sample_map(self, spot_id: int, width: int = 10, height: int = 10, objects: List[WorldObject] = None, gateways: List[Gateway] = None, terrain_type: TerrainType = None):
        tiles = {}
        for x in range(width):
            for y in range(height):
                coord = Coordinate(x, y, 0)
                tiles[coord] = Tile(coord, terrain_type or TerrainType.grass())
        
        return PhysicalMapAggregate(
            spot_id=SpotId(spot_id),
            tiles=tiles,
            objects=objects or [],
            gateways=gateways or []
        )

    def _register_spots(self, spot_repo, spots_data: List[Dict]):
        """SpotRepository にスポットを登録する"""
        for s in spots_data:
            spot_repo.save(Spot(SpotId(s["id"]), s["name"], s.get("desc", "")))

    def _create_player_object(self, player_id: int, x: int = 0, y: int = 0):
        """プレイヤー用の WorldObject。Gateway ハンドラがプレイヤー判定するため player_id を渡す"""
        return WorldObject(
            object_id=WorldObjectId.create(player_id),
            coordinate=Coordinate(x, y, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(
                direction=DirectionEnum.SOUTH,
                player_id=PlayerId(player_id),
            ),
        )

    def _create_pursuit_snapshot(self, target_id: int = 200, spot_id: int = 1, x: int = 2, y: int = 0):
        return PursuitTargetSnapshot(
            target_id=WorldObjectId.create(target_id),
            spot_id=SpotId(spot_id),
            coordinate=Coordinate(x, y, 0),
        )

    def test_move_tile_success_and_dto_completeness(self, setup_service):
        """タイルベースの移動が成功し、DTOが完全に埋まっていること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, uow, _, event_publisher = setup_service

        player_id = 1
        spot_id = 1
        # プロフィールとスポットの準備
        profile = self._create_sample_profile(player_id, "Alice")
        profile_repo.save(profile)

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Starting Village"}])
        
        # プレイヤー状態と物理マップの準備
        status = self._create_sample_status(player_id, spot_id, 0, 0)
        status_repo.save(status)
        
        player_obj = self._create_player_object(player_id, 0, 0)
        phys_map = self._create_sample_map(spot_id, objects=[player_obj])
        phys_repo.save(phys_map)
        
        # 南に移動
        command = MoveTileCommand(player_id=player_id, direction=DirectionEnum.SOUTH)
        result = service.move_tile(command)
        
        assert result.success is True
        assert result.player_name == "Alice"
        assert result.from_spot_name == "Starting Village"
        assert result.to_spot_name == "Starting Village"
        assert result.to_coordinate == {"x": 0, "y": 1, "z": 0}
        assert result.busy_until_tick > 100

        # ドメインイベントの検証
        events = event_publisher.get_published_events()
        assert any(isinstance(e, WorldObjectMovedEvent) for e in events)
        assert any(isinstance(e, PlayerLocationChangedEvent) for e in events)
        assert any(isinstance(e, PlayerStaminaConsumedEvent) for e in events)

    def test_find_correct_spot_set_destination_same_spot(self, setup_service):
        """同一スポット内で目的地設定が正しく動作すること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot1_id = 101
        spot2_id = 201

        self._register_spots(spot_repo, [{"id": spot1_id, "name": "World 1 Spot"}, {"id": spot2_id, "name": "World 2 Spot"}])

        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot2_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot2_id, objects=[self._create_player_object(player_id)]))

        command = SetDestinationCommand(player_id=player_id, destination_type="spot", target_spot_id=spot2_id)
        result = service.set_destination(command)

        assert result.success is True
        assert result.to_spot_id == spot2_id
        assert "既に目的地のスポットにいます" in result.message

    def test_set_destination_player_not_on_map(self, setup_service):
        """プレイヤーがどのマップにも配置されていない場合、エラーになること"""
        service, world_query_service, status_repo, profile_repo, _, spot_repo, _, _, _ = setup_service
        
        player_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(
            player_id, navigation_state=PlayerNavigationState.empty()
        )
        status_repo.save(status)
        
        command = SetDestinationCommand(player_id=player_id, destination_type="spot", target_spot_id=1)
        with pytest.raises(MovementInvalidException, match="not placed on any map"):
            service.set_destination(command)

    def test_move_to_destination_delegates_to_set_destination_same_spot(self, setup_service):
        """move_to_destination は set_destination に委譲し、同一スポット時は同じ結果を返すこと"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service
        player_id = 1
        spot1_id = 101
        spot2_id = 201
        self._register_spots(spot_repo, [{"id": spot1_id, "name": "World 1 Spot"}, {"id": spot2_id, "name": "World 2 Spot"}])
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot2_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot2_id, objects=[self._create_player_object(player_id)]))
        result = service.move_to_destination(player_id, "spot", spot2_id)
        assert result.success is True
        assert result.to_spot_id == spot2_id
        assert "既に目的地のスポットにいます" in result.message

    def test_move_to_destination_invalid_destination_type_raises(self, setup_service):
        """move_to_destination で destination_type が spot/location 以外なら MovementInvalidException"""
        service, *_ = setup_service
        with pytest.raises(MovementInvalidException, match="spot.*location"):
            service.move_to_destination(1, "invalid", 2)

    def test_move_to_destination_location_without_area_id_raises(self, setup_service):
        """move_to_destination で destination_type=location かつ target_location_area_id なしなら MovementInvalidException"""
        service, *_ = setup_service
        with pytest.raises(MovementInvalidException, match="target_location_area_id"):
            service.move_to_destination(1, "location", 2, target_location_area_id=None)

    def test_move_tile_player_object_missing_from_map(self, setup_service):
        """プレイヤー状態はあるが物理マップ上にオブジェクトがない場合、エラーになること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service
        
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id))
        
        # 物理マップはあるが、プレイヤーオブジェクトを入れない
        phys_map = self._create_sample_map(spot_id, objects=[])
        phys_repo.save(phys_map)
        
        command = MoveTileCommand(player_id=player_id, direction=DirectionEnum.SOUTH)
        with pytest.raises(MovementInvalidException, match="Player object not found"):
            service.move_tile(command)

    def test_move_tile_out_of_bounds(self, setup_service):
        """マップ範囲外への移動が失敗し、例外が発生すること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service
        
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        
        # 1x1の極小マップを作成
        phys_map = self._create_sample_map(spot_id, width=1, height=1, objects=[self._create_player_object(player_id, 0, 0)])
        phys_repo.save(phys_map)
        
        command = MoveTileCommand(player_id=player_id, direction=DirectionEnum.SOUTH)
        with pytest.raises(PathBlockedException):
            service.move_tile(command)

    def test_tick_movement_failure_context_in_dto(self, setup_service):
        """tick_movement 失敗時の DTO にプレイヤー名などのコンテキストが含まれること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service
        
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id, "Charlie"))
        status = self._create_sample_status(player_id, spot_id, 0, 0)
        # 予め経路を設定しておくが、わざと行き止まりにする
        status.set_destination(Coordinate(1, 0, 0), [Coordinate(0, 0, 0), Coordinate(1, 0, 0)], None, None, None)
        status_repo.save(status)
        
        # (1, 0) が壁のマップ
        tiles = {Coordinate(0, 0, 0): Tile(Coordinate(0, 0, 0), TerrainType.grass()),
                 Coordinate(1, 0, 0): Tile(Coordinate(1, 0, 0), TerrainType.wall())}
        phys_map = PhysicalMapAggregate(spot_id=SpotId(spot_id), tiles=tiles, 
                                      objects=[self._create_player_object(player_id, 0, 0)])
        phys_repo.save(phys_map)
        
        result = service.tick_movement(TickMovementCommand(player_id=player_id))
        
        assert result.success is False
        assert result.player_name == "Charlie"
        assert result.from_spot_id == spot_id
        assert "は通行できません" in result.error_message

    def test_movement_cost_affects_busy_tick(self, setup_service):
        """地形コストが到着ティック（busy_until_tick）に影響すること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, _, time_provider, _ = setup_service
        
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        
        # 沼地（コスト高）のマップ
        swamp_map = self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)], terrain_type=TerrainType.swamp())
        phys_repo.save(swamp_map)
        
        command = MoveTileCommand(player_id=player_id, direction=DirectionEnum.SOUTH)
        result = service.move_tile(command)
        
        assert result.success is True
        # 沼地の基本コストは 5.0 なので、busy_until_tick は 100 + 5 = 105 になるはず
        assert result.busy_until_tick == 105

    def test_set_destination_and_tick_movement_persists_path(self, setup_service):
        """目的地と経路が集約に保存され、複数ステップの移動が可能であること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, _, time_provider, _ = setup_service

        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id, spot_id, 0, 0)
        status_repo.save(status)

        # ロケーションエリア (2,0) を含む領域を追加して経路目標にする
        location_area = LocationArea(
            location_id=LocationAreaId(10),
            name="Goal",
            description="",
            area=RectArea.from_coordinates(Coordinate(2, 0, 0), Coordinate(2, 0, 0)),
        )
        phys_map = self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)])
        phys_map.add_location_area(location_area)
        phys_repo.save(phys_map)
        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])

        # 目的地をロケーション指定で設定
        service.set_destination(SetDestinationCommand(player_id=player_id, destination_type="location", target_spot_id=spot_id, target_location_area_id=10))

        # 集約を確認
        saved_status = status_repo.find_by_id(PlayerId(player_id))
        assert saved_status.current_destination == Coordinate(2, 0, 0)
        initial_path_len = len(saved_status.planned_path)
        assert initial_path_len > 0

        # 1ステップ目
        res1 = service.tick_movement(TickMovementCommand(player_id=player_id))
        assert res1.success is True
        assert res1.to_coordinate == {"x": 1, "y": 0, "z": 0}

        # 状態が更新されているか（パスが短くなっているか）
        status_after_step = status_repo.find_by_id(PlayerId(player_id))
        assert len(status_after_step.planned_path) < initial_path_len

    def test_set_destination_object_paths_to_object_and_arrival_clears_path(self, setup_service):
        """destination_type=object でオブジェクトへ経路設定し、隣接到着で経路がクリアされること"""
        service, _, status_repo, profile_repo, phys_repo, spot_repo, _, time_provider, _ = setup_service

        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id, spot_id, 0, 0)
        status_repo.save(status)

        chest_obj = WorldObject(
            object_id=WorldObjectId(200),
            coordinate=Coordinate(2, 0, 0),
            object_type=ObjectTypeEnum.CHEST,
            component=ChestComponent(is_open=False, item_ids=[]),
        )
        phys_map = self._create_sample_map(
            spot_id,
            objects=[
                self._create_player_object(player_id, 0, 0),
                chest_obj,
            ],
        )
        phys_repo.save(phys_map)
        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])

        service.set_destination(
            SetDestinationCommand(
                player_id=player_id,
                destination_type="object",
                target_spot_id=spot_id,
                target_world_object_id=200,
            )
        )

        saved_status = status_repo.find_by_id(PlayerId(player_id))
        chest_coord = Coordinate(2, 0, 0)
        # current_destination はオブジェクト隣接の通行可能セル（オブジェクト座標は通行不可のため）
        assert saved_status.current_destination.distance_to(chest_coord) == 1
        assert saved_status.goal_world_object_id == WorldObjectId(200)
        assert len(saved_status.planned_path) > 0

        res1 = service.tick_movement(TickMovementCommand(player_id=player_id))
        assert res1.success is True
        assert res1.to_coordinate == {"x": 1, "y": 0, "z": 0}

        status_after = status_repo.find_by_id(PlayerId(player_id))
        assert status_after.planned_path == []
        assert status_after.goal_spot_id is None

    def test_tick_movement_clears_static_path_without_erasing_pursuit_state(self, setup_service):
        """静的移動の到着処理で経路が消えても追跡状態は残ること"""
        service, _, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id, spot_id, 0, 0)
        status.start_pursuit(self._create_pursuit_snapshot())
        status_repo.save(status)

        chest_obj = WorldObject(
            object_id=WorldObjectId(200),
            coordinate=Coordinate(2, 0, 0),
            object_type=ObjectTypeEnum.CHEST,
            component=ChestComponent(is_open=False, item_ids=[]),
        )
        phys_map = self._create_sample_map(
            spot_id,
            objects=[
                self._create_player_object(player_id, 0, 0),
                chest_obj,
            ],
        )
        phys_repo.save(phys_map)
        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])

        service.set_destination(
            SetDestinationCommand(
                player_id=player_id,
                destination_type="object",
                target_spot_id=spot_id,
                target_world_object_id=200,
            )
        )

        saved_before = status_repo.find_by_id(PlayerId(player_id))
        assert saved_before.pursuit_state is not None
        assert len(saved_before.planned_path) > 0

        result = service.tick_movement(TickMovementCommand(player_id=player_id))

        assert result.success is True
        saved_after = status_repo.find_by_id(PlayerId(player_id))
        assert saved_after.planned_path == []
        assert saved_after.current_destination is None
        assert saved_after.pursuit_state is not None
        assert saved_after.pursuit_state.target_id == WorldObjectId(200)

    def test_replan_path_to_coordinate_in_current_unit_of_work_sets_pursuit_path(
        self, setup_service
    ):
        service, _, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(
            self._create_sample_map(
                spot_id,
                width=4,
                height=2,
                objects=[self._create_player_object(player_id, 0, 0)],
            )
        )
        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])

        result = service.replan_path_to_coordinate_in_current_unit_of_work(
            player_id=player_id,
            target_spot_id=spot_id,
            target_coordinate=Coordinate(3, 0, 0),
        )

        assert result.success is True
        assert result.path_planned is True
        assert result.already_at_destination is False
        saved_status = status_repo.find_by_id(PlayerId(player_id))
        assert saved_status.goal_spot_id == SpotId(spot_id)
        assert saved_status.planned_path[-1] == Coordinate(3, 0, 0)

    def test_replan_path_to_coordinate_in_current_unit_of_work_clears_path_when_unreachable(
        self, setup_service
    ):
        service, _, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id, spot_id, 0, 0)
        status.set_destination(
            Coordinate(1, 0, 0),
            [Coordinate(0, 0, 0), Coordinate(1, 0, 0)],
            goal_spot_id=SpotId(spot_id),
        )
        status_repo.save(status)

        wall_tiles = {
            Coordinate(0, 0, 0): Tile(Coordinate(0, 0, 0), TerrainType.grass()),
            Coordinate(1, 0, 0): Tile(Coordinate(1, 0, 0), TerrainType.wall()),
            Coordinate(2, 0, 0): Tile(Coordinate(2, 0, 0), TerrainType.wall()),
        }
        phys_repo.save(
            PhysicalMapAggregate(
                spot_id=SpotId(spot_id),
                tiles=wall_tiles,
                objects=[self._create_player_object(player_id, 0, 0)],
            )
        )
        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])

        result = service.replan_path_to_coordinate_in_current_unit_of_work(
            player_id=player_id,
            target_spot_id=spot_id,
            target_coordinate=Coordinate(2, 0, 0),
        )

        assert result.success is False
        assert result.path_planned is False
        assert result.already_at_destination is False
        saved_status = status_repo.find_by_id(PlayerId(player_id))
        assert saved_status.planned_path == []
        assert saved_status.goal_spot_id is None

    def test_replan_path_to_coordinate_unreachable_keeps_pursuit_state_intact(
        self, setup_service
    ):
        service, _, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id, spot_id, 0, 0)
        status.start_pursuit(self._create_pursuit_snapshot(target_id=250, x=2, y=0))
        status.set_destination(
            Coordinate(1, 0, 0),
            [Coordinate(0, 0, 0), Coordinate(1, 0, 0)],
            goal_spot_id=SpotId(spot_id),
        )
        status_repo.save(status)

        wall_tiles = {
            Coordinate(0, 0, 0): Tile(Coordinate(0, 0, 0), TerrainType.grass()),
            Coordinate(1, 0, 0): Tile(Coordinate(1, 0, 0), TerrainType.wall()),
            Coordinate(2, 0, 0): Tile(Coordinate(2, 0, 0), TerrainType.wall()),
        }
        phys_repo.save(
            PhysicalMapAggregate(
                spot_id=SpotId(spot_id),
                tiles=wall_tiles,
                objects=[self._create_player_object(player_id, 0, 0)],
            )
        )
        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])

        result = service.replan_path_to_coordinate_in_current_unit_of_work(
            player_id=player_id,
            target_spot_id=spot_id,
            target_coordinate=Coordinate(2, 0, 0),
        )

        assert result.success is False
        saved_status = status_repo.find_by_id(PlayerId(player_id))
        assert saved_status.planned_path == []
        assert saved_status.pursuit_state is not None
        assert saved_status.pursuit_state.target_id == WorldObjectId(250)

    def test_replan_path_to_coordinate_recovers_after_pursuit_path_was_cleared(
        self, setup_service
    ):
        service, _, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id, spot_id, 0, 0)
        status.start_pursuit(self._create_pursuit_snapshot(target_id=251, x=3, y=0))
        status.clear_path()
        status_repo.save(status)
        phys_repo.save(
            self._create_sample_map(
                spot_id,
                width=4,
                height=2,
                objects=[self._create_player_object(player_id, 0, 0)],
            )
        )
        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])

        result = service.replan_path_to_coordinate_in_current_unit_of_work(
            player_id=player_id,
            target_spot_id=spot_id,
            target_coordinate=Coordinate(3, 0, 0),
        )

        saved_status = status_repo.find_by_id(PlayerId(player_id))
        assert result.success is True
        assert result.path_planned is True
        assert result.already_at_destination is False
        assert saved_status is not None
        assert saved_status.goal_spot_id == SpotId(spot_id)
        assert saved_status.planned_path[-1] == Coordinate(3, 0, 0)
        assert saved_status.pursuit_state is not None
        assert saved_status.pursuit_state.target_id == WorldObjectId(251)

    def test_tick_movement_location_area_not_found_clears_path(self, setup_service):
        """到着判定で LocationAreaNotFoundException のとき経路をクリアして「目標はもう存在しない」とみなす"""
        service, _, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id, spot_id, 0, 0)
        status_repo.save(status)

        location_area = LocationArea(
            location_id=LocationAreaId(20),
            name="Goal",
            description="",
            area=RectArea.from_coordinates(Coordinate(2, 0, 0), Coordinate(2, 0, 0)),
        )
        phys_map = self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)])
        phys_map.add_location_area(location_area)
        phys_repo.save(phys_map)
        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])

        service.set_destination(
            SetDestinationCommand(
                player_id=player_id,
                destination_type="location",
                target_spot_id=spot_id,
                target_location_area_id=20,
            )
        )
        saved_before = status_repo.find_by_id(PlayerId(player_id))
        assert len(saved_before.planned_path) > 0

        # ロケーションエリアを削除したマップで上書き（到着判定で LocationAreaNotFoundException が発生する）
        phys_map_no_location = self._create_sample_map(
            spot_id, objects=[self._create_player_object(player_id, 0, 0)]
        )
        phys_repo.save(phys_map_no_location)

        result = service.tick_movement(TickMovementCommand(player_id=player_id))

        assert result.success is True
        assert result.to_coordinate == {"x": 1, "y": 0, "z": 0}
        saved_after = status_repo.find_by_id(PlayerId(player_id))
        assert saved_after.planned_path == []
        assert saved_after.goal_spot_id is None

    def test_tick_movement_object_not_found_clears_path(self, setup_service):
        """到着判定で ObjectNotFoundException のとき経路をクリアして「目標はもう存在しない」とみなす"""
        service, _, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id, spot_id, 0, 0)
        status_repo.save(status)

        chest_obj = WorldObject(
            object_id=WorldObjectId(201),
            coordinate=Coordinate(2, 0, 0),
            object_type=ObjectTypeEnum.CHEST,
            component=ChestComponent(is_open=False, item_ids=[]),
        )
        phys_map = self._create_sample_map(
            spot_id,
            objects=[
                self._create_player_object(player_id, 0, 0),
                chest_obj,
            ],
        )
        phys_repo.save(phys_map)
        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])

        service.set_destination(
            SetDestinationCommand(
                player_id=player_id,
                destination_type="object",
                target_spot_id=spot_id,
                target_world_object_id=201,
            )
        )
        saved_before = status_repo.find_by_id(PlayerId(player_id))
        assert len(saved_before.planned_path) > 0

        # オブジェクトを削除したマップで上書き（到着判定で ObjectNotFoundException が発生する）
        phys_map_no_object = self._create_sample_map(
            spot_id, objects=[self._create_player_object(player_id, 0, 0)]
        )
        phys_repo.save(phys_map_no_object)

        result = service.tick_movement(TickMovementCommand(player_id=player_id))

        assert result.success is True
        assert result.to_coordinate == {"x": 1, "y": 0, "z": 0}
        saved_after = status_repo.find_by_id(PlayerId(player_id))
        assert saved_after.planned_path == []
        assert saved_after.goal_world_object_id is None

    def test_tick_movement_arrival_check_unexpected_exception_propagates(self, setup_service):
        """到着判定で想定外の例外（LocationAreaNotFoundException/ObjectNotFoundException 以外）は伝播すること"""
        service, _, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id, spot_id, 0, 0)
        status_repo.save(status)

        location_area = LocationArea(
            location_id=LocationAreaId(30),
            name="Goal",
            description="",
            area=RectArea.from_coordinates(Coordinate(2, 0, 0), Coordinate(2, 0, 0)),
        )
        phys_map = self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)])
        phys_map.add_location_area(location_area)
        phys_repo.save(phys_map)
        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])

        service.set_destination(
            SetDestinationCommand(
                player_id=player_id,
                destination_type="location",
                target_spot_id=spot_id,
                target_location_area_id=30,
            )
        )

        # get_location_area が RuntimeError を投げるようにパッチ
        with patch.object(
            phys_map,
            "get_location_area",
            side_effect=RuntimeError("unexpected in get_location_area"),
        ):
            # find_by_spot_id がこのパッチ済みマップを返すようにするには、
            # リポジトリをパッチする必要がある
            with patch.object(
                phys_repo,
                "find_by_spot_id",
                return_value=phys_map,
            ):
                with pytest.raises(WorldSystemErrorException) as exc_info:
                    service.tick_movement(TickMovementCommand(player_id=player_id))
                assert exc_info.value.original_exception is not None
                assert isinstance(exc_info.value.original_exception, RuntimeError)

    def test_set_destination_object_already_adjacent_returns_success(self, setup_service):
        """オブジェクトに既に隣接しているとき destination_type=object で「既に傍にいます」が返ること"""
        service, _, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id, spot_id, 1, 0)
        status_repo.save(status)

        chest_obj = WorldObject(
            object_id=WorldObjectId(200),
            coordinate=Coordinate(2, 0, 0),
            object_type=ObjectTypeEnum.CHEST,
            component=ChestComponent(is_open=False, item_ids=[]),
        )
        phys_map = self._create_sample_map(
            spot_id,
            objects=[
                self._create_player_object(player_id, 1, 0),
                chest_obj,
            ],
        )
        phys_repo.save(phys_map)
        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])

        result = service.set_destination(
            SetDestinationCommand(
                player_id=player_id,
                destination_type="object",
                target_spot_id=spot_id,
                target_world_object_id=200,
            )
        )

        assert result.success is True
        assert "既に目標オブジェクトの傍にいます" in result.message

    def test_set_destination_object_not_found_raises(self, setup_service):
        """オブジェクトがマップに存在しないとき MovementInvalidException"""
        service, _, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id, spot_id, 0, 0)
        status_repo.save(status)

        phys_map = self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)])
        phys_repo.save(phys_map)
        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])

        with pytest.raises(MovementInvalidException, match="Object 999 not found"):
            service.set_destination(
                SetDestinationCommand(
                    player_id=player_id,
                    destination_type="object",
                    target_spot_id=spot_id,
                    target_world_object_id=999,
                )
            )

    def test_cancel_movement_clears_path_and_returns_success(self, setup_service):
        """cancel_movement で経路がクリアされ、成功 DTO が返ること"""
        service, _, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id, "Alice"))
        status = self._create_sample_status(player_id, spot_id, 0, 0)
        status_repo.save(status)

        location_area = LocationArea(
            location_id=LocationAreaId(10),
            name="Goal",
            description="",
            area=RectArea.from_coordinates(Coordinate(2, 0, 0), Coordinate(2, 0, 0)),
        )
        phys_map = self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)])
        phys_map.add_location_area(location_area)
        phys_repo.save(phys_map)
        self._register_spots(spot_repo, [{"id": spot_id, "name": "Spot 1"}])

        service.set_destination(
            SetDestinationCommand(
                player_id=player_id,
                destination_type="location",
                target_spot_id=spot_id,
                target_location_area_id=10,
            )
        )
        saved_before = status_repo.find_by_id(PlayerId(player_id))
        assert saved_before.goal_spot_id is not None

        result = service.cancel_movement(CancelMovementCommand(player_id=player_id))

        assert result.success is True
        assert "中断" in result.message
        saved_after = status_repo.find_by_id(PlayerId(player_id))
        assert saved_after.goal_spot_id is None
        assert saved_after.planned_path == []

    def test_cancel_movement_player_not_found_raises(self, setup_service):
        """cancel_movement でプレイヤーが存在しない場合 PlayerNotFoundException"""
        service, _, status_repo, _, _, spot_repo, _, _, _ = setup_service

        self._register_spots(spot_repo, [{"id": 1, "name": "Spot 1"}])
        # プレイヤーを登録しない
        command = CancelMovementCommand(player_id=999)
        with pytest.raises(PlayerNotFoundException):
            service.cancel_movement(command)

    def test_cancel_movement_when_no_current_spot_returns_failure_dto(self, setup_service):
        """cancel_movement で経路クリア後も現在地が取得できない場合、失敗 DTO を返す（キャンセルは成功）"""
        service, _, status_repo, profile_repo, _, spot_repo, _, _, _ = setup_service

        player_id = 1
        profile_repo.save(self._create_sample_profile(player_id, "Alice"))
        status = self._create_sample_status(
            player_id, navigation_state=PlayerNavigationState.empty()
        )
        status_repo.save(status)

        result = service.cancel_movement(CancelMovementCommand(player_id=player_id))

        assert result.success is False
        assert "現在地が不明です" in result.error_message
        # 経路はクリアされている
        saved = status_repo.find_by_id(PlayerId(player_id))
        assert saved.goal_spot_id is None
        assert saved.planned_path == []

    def test_cancel_movement_command_player_id_invalid_raises(self):
        """CancelMovementCommand の player_id が 0 以下の場合 ValueError"""
        with pytest.raises(ValueError, match="player_id must be greater than 0"):
            CancelMovementCommand(player_id=0)

    def test_gateway_transition_uses_service(self, setup_service):
        """ゲートウェイ移動がドメインサービスを通じて正しく処理されること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot1_id = 1
        spot2_id = 2

        gateway = Gateway(
            gateway_id=GatewayId(101),
            name="To Spot 2",
            area=RectArea.from_coordinates(Coordinate(1, 0, 0), Coordinate(1, 0, 0)),
            target_spot_id=SpotId(spot2_id),
            landing_coordinate=Coordinate(5, 5, 0)
        )

        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot1_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot1_id, objects=[self._create_player_object(player_id)], gateways=[gateway]))
        phys_repo.save(self._create_sample_map(spot2_id))
        self._register_spots(spot_repo, [{"id": spot1_id, "name": "Spot 1"}, {"id": spot2_id, "name": "Spot 2"}])
        
        # 移動
        result = service.move_tile(MoveTileCommand(player_id=player_id, direction=DirectionEnum.EAST))
        
        assert result.success is True
        assert result.to_spot_id == spot2_id
        assert result.to_spot_name == "Spot 2"
        assert result.to_coordinate == {"x": 5, "y": 5, "z": 0}
        
        # パスがクリアされていること（スポット跨ぎ後は再プランニングが必要）
        updated_status = status_repo.find_by_id(PlayerId(player_id))
        assert updated_status.planned_path == []
        assert updated_status.current_destination is None

    def test_gateway_transition_blocked_by_require_toll(self, setup_service_with_transition_policy):
        """ゲートウェイに RequireToll 条件があり所持金が不足している場合、失敗 DTO が返ること"""
        service, status_repo, profile_repo, phys_repo, spot_repo, policy_repo, _, _, _ = setup_service_with_transition_policy
        player_id = 1
        spot1_id = 1
        spot2_id = 2
        gateway = Gateway(
            gateway_id=GatewayId(101),
            name="To Spot 2",
            area=RectArea.from_coordinates(Coordinate(1, 0, 0), Coordinate(1, 0, 0)),
            target_spot_id=SpotId(spot2_id),
            landing_coordinate=Coordinate(5, 5, 0),
        )
        policy_repo.set_conditions(SpotId(spot1_id), SpotId(spot2_id), [RequireToll(amount_gold=5000)])
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id, spot1_id, 0, 0)
        assert status.gold.value == 1000
        status_repo.save(status)
        phys_repo.save(self._create_sample_map(spot1_id, objects=[self._create_player_object(player_id)], gateways=[gateway]))
        phys_repo.save(self._create_sample_map(spot2_id))
        self._register_spots(spot_repo, [{"id": spot1_id, "name": "Spot 1"}, {"id": spot2_id, "name": "Spot 2"}])

        result = service.move_tile(MoveTileCommand(player_id=player_id, direction=DirectionEnum.EAST))

        assert result.success is False
        assert "通行料" in result.error_message
        assert "5000" in result.error_message
        updated_status = status_repo.find_by_id(PlayerId(player_id))
        assert updated_status.current_spot_id == SpotId(spot1_id)
        assert updated_status.current_coordinate == Coordinate(0, 0, 0)

    def test_gateway_transition_allowed_with_sufficient_toll(self, setup_service_with_transition_policy):
        """ゲートウェイに RequireToll 条件があり所持金が足りる場合、遷移が成功すること"""
        service, status_repo, profile_repo, phys_repo, spot_repo, policy_repo, _, _, _ = setup_service_with_transition_policy
        player_id = 1
        spot1_id = 1
        spot2_id = 2
        gateway = Gateway(
            gateway_id=GatewayId(101),
            name="To Spot 2",
            area=RectArea.from_coordinates(Coordinate(1, 0, 0), Coordinate(1, 0, 0)),
            target_spot_id=SpotId(spot2_id),
            landing_coordinate=Coordinate(5, 5, 0),
        )
        policy_repo.set_conditions(SpotId(spot1_id), SpotId(spot2_id), [RequireToll(amount_gold=100)])
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot1_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot1_id, objects=[self._create_player_object(player_id)], gateways=[gateway]))
        phys_repo.save(self._create_sample_map(spot2_id))
        self._register_spots(spot_repo, [{"id": spot1_id, "name": "Spot 1"}, {"id": spot2_id, "name": "Spot 2"}])

        result = service.move_tile(MoveTileCommand(player_id=player_id, direction=DirectionEnum.EAST))

        assert result.success is True
        assert result.to_spot_id == spot2_id
        assert result.to_spot_name == "Spot 2"

    def test_gateway_transition_blocked_by_weather(self, setup_service_with_transition_policy):
        """ゲートウェイに BlockIfWeather 条件があり該当天候の場合、失敗 DTO が返ること"""
        service, status_repo, profile_repo, phys_repo, spot_repo, policy_repo, _, _, _ = setup_service_with_transition_policy
        player_id = 1
        spot1_id = 1
        spot2_id = 2
        gateway = Gateway(
            gateway_id=GatewayId(101),
            name="To Spot 2",
            area=RectArea.from_coordinates(Coordinate(1, 0, 0), Coordinate(1, 0, 0)),
            target_spot_id=SpotId(spot2_id),
            landing_coordinate=Coordinate(5, 5, 0),
        )
        policy_repo.set_conditions(
            SpotId(spot1_id), SpotId(spot2_id),
            [block_if_weather([WeatherTypeEnum.BLIZZARD, WeatherTypeEnum.STORM])],
        )
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot1_id, 0, 0))
        phys_map = self._create_sample_map(spot1_id, objects=[self._create_player_object(player_id)], gateways=[gateway])
        phys_map.set_weather(WeatherState(WeatherTypeEnum.BLIZZARD, 1.0))
        phys_repo.save(phys_map)
        phys_repo.save(self._create_sample_map(spot2_id))
        self._register_spots(spot_repo, [{"id": spot1_id, "name": "Spot 1"}, {"id": spot2_id, "name": "Spot 2"}])

        result = service.move_tile(MoveTileCommand(player_id=player_id, direction=DirectionEnum.EAST))

        assert result.success is False
        assert "悪天候" in result.error_message or "通行止め" in result.error_message
        updated_status = status_repo.find_by_id(PlayerId(player_id))
        assert updated_status.current_spot_id == SpotId(spot1_id)

    def test_gateway_transition_allowed_when_weather_clear(self, setup_service_with_transition_policy):
        """ゲートウェイに BlockIfWeather 条件があり天候が該当しない場合、遷移が成功すること"""
        service, status_repo, profile_repo, phys_repo, spot_repo, policy_repo, _, _, _ = setup_service_with_transition_policy
        player_id = 1
        spot1_id = 1
        spot2_id = 2
        gateway = Gateway(
            gateway_id=GatewayId(101),
            name="To Spot 2",
            area=RectArea.from_coordinates(Coordinate(1, 0, 0), Coordinate(1, 0, 0)),
            target_spot_id=SpotId(spot2_id),
            landing_coordinate=Coordinate(5, 5, 0),
        )
        policy_repo.set_conditions(
            SpotId(spot1_id), SpotId(spot2_id),
            [block_if_weather([WeatherTypeEnum.BLIZZARD])],
        )
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot1_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot1_id, objects=[self._create_player_object(player_id)], gateways=[gateway]))
        phys_repo.save(self._create_sample_map(spot2_id))
        self._register_spots(spot_repo, [{"id": spot1_id, "name": "Spot 1"}, {"id": spot2_id, "name": "Spot 2"}])

        result = service.move_tile(MoveTileCommand(player_id=player_id, direction=DirectionEnum.EAST))

        assert result.success is True
        assert result.to_spot_id == spot2_id

    def test_gateway_transition_without_policy_unchanged(self, setup_service):
        """遷移ポリシーを渡していない場合、従来どおりゲートウェイ通過が成功すること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service
        player_id = 1
        spot1_id = 1
        spot2_id = 2
        gateway = Gateway(
            gateway_id=GatewayId(101),
            name="To Spot 2",
            area=RectArea.from_coordinates(Coordinate(1, 0, 0), Coordinate(1, 0, 0)),
            target_spot_id=SpotId(spot2_id),
            landing_coordinate=Coordinate(5, 5, 0),
        )
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot1_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot1_id, objects=[self._create_player_object(player_id)], gateways=[gateway]))
        phys_repo.save(self._create_sample_map(spot2_id))
        self._register_spots(spot_repo, [{"id": spot1_id, "name": "Spot 1"}, {"id": spot2_id, "name": "Spot 2"}])

        result = service.move_tile(MoveTileCommand(player_id=player_id, direction=DirectionEnum.EAST))

        assert result.success is True
        assert result.to_spot_id == spot2_id

    def test_domain_exception_handling(self, setup_service):
        """ドメイン例外が適切にキャッチされ、失敗DTOとして返されること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service
        
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id, spot_id, 0, 0)
        # 戦闘不能にする
        status.apply_damage(1000)
        status_repo.save(status)
        
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))
        
        result = service.move_tile(MoveTileCommand(player_id=player_id, direction=DirectionEnum.SOUTH))
        
        assert result.success is False
        assert "行動できません" in result.error_message

    def test_get_player_location_populates_all_names(self, setup_service):
        """現在地取得時に全ての名前情報が正しく取得できること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id, "Bob"))
        status_repo.save(self._create_sample_status(player_id, spot_id, 3, 4))

        self._register_spots(spot_repo, [{"id": spot_id, "name": "Secret Base", "desc": "Hidden location"}])
        
        loc = world_query_service.get_player_location(GetPlayerLocationQuery(player_id=player_id))

        assert loc is not None
        assert loc.player_name == "Bob"
        assert loc.current_spot_name == "Secret Base"
        assert loc.current_spot_description == "Hidden location"
        assert loc.x == 3
        assert loc.y == 4

    def test_get_player_location_returns_none_when_not_placed(self, setup_service):
        """プレイヤーが未配置（current_spot_id または current_coordinate が None）の場合は None を返すこと"""
        service, world_query_service, status_repo, profile_repo, _, spot_repo, _, _, _ = setup_service

        player_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(
            player_id, navigation_state=PlayerNavigationState.empty()
        )
        status_repo.save(status)

        loc = world_query_service.get_player_location(GetPlayerLocationQuery(player_id=player_id))
        assert loc is None

    def test_get_player_location_returns_none_when_player_not_found(self, setup_service):
        """存在しないプレイヤーIDで get_player_location を呼んだ場合も None を返すこと（未配置扱い）"""
        service, world_query_service, _, _, _, _, _, _, _ = setup_service

        loc = world_query_service.get_player_location(GetPlayerLocationQuery(player_id=99999))
        assert loc is None

    def test_multi_spot_pathfinding_initial_step(self, setup_service):
        """スポットを跨ぐ目的地設定時に、まずゲートウェイを目指すパスが生成されること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot1_id = 1
        spot2_id = 2

        gateway = Gateway(
            gateway_id=GatewayId(101),
            name="To Spot 2",
            area=RectArea.from_coordinates(Coordinate(5, 0, 0), Coordinate(5, 0, 0)),
            target_spot_id=SpotId(spot2_id),
            landing_coordinate=Coordinate(0, 0, 0)
        )

        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot1_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot1_id, objects=[self._create_player_object(player_id)], gateways=[gateway]))
        phys_repo.save(self._create_sample_map(spot2_id))
        self._register_spots(spot_repo, [{"id": spot1_id, "name": "Spot 1"}, {"id": spot2_id, "name": "Spot 2"}])
        
        # 別スポットを目的地に設定（スポット指定で座標不要）
        service.set_destination(SetDestinationCommand(player_id=player_id, destination_type="spot", target_spot_id=spot2_id))
        
        updated_status = status_repo.find_by_id(PlayerId(player_id))
        # 目的地がゲートウェイの座標になっていること
        assert updated_status.current_destination == Coordinate(5, 0, 0)
        # パスが生成されていること
        assert len(updated_status.planned_path) > 1

    def test_player_not_found(self, setup_service):
        """存在しないプレイヤーを指定した場合に PlayerNotFoundException が発生すること"""
        service, world_query_service, _, _, _, spot_repo, _, _, _ = setup_service
        
        with pytest.raises(PlayerNotFoundException):
            service.move_tile(MoveTileCommand(player_id=999, direction=DirectionEnum.NORTH))

    def test_map_not_found(self, setup_service):
        """プレイヤーがいるはずのマップが存在しない場合に MapNotFoundException が発生すること"""
        service, world_query_service, status_repo, profile_repo, _, spot_repo, _, _, _ = setup_service
        
        player_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        # マップID 999 にプレイヤーを配置するが、その物理マップは作成しない
        status_repo.save(self._create_sample_status(player_id, spot_id=999, x=0, y=0))
        
        with pytest.raises(MapNotFoundException):
            service.move_tile(MoveTileCommand(player_id=player_id, direction=DirectionEnum.NORTH))

    def test_stamina_exhaustion(self, setup_service):
        """スタミナ不足時に PlayerStaminaExhaustedException が発生すること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service
        
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        
        # スタミナを 0 にする
        status = self._create_sample_status(player_id, spot_id, 0, 0)
        status.consume_stamina(100)
        status_repo.save(status)
        
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))
        
        with pytest.raises(PlayerStaminaExhaustedException):
            service.move_tile(MoveTileCommand(player_id=player_id, direction=DirectionEnum.SOUTH))

    def test_path_blocked_by_wall(self, setup_service):
        """壁などの障害物がある場合に PathBlockedException が発生すること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service
        
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        
        # 南側が壁のマップを作成
        tiles = {}
        for x in range(5):
            for y in range(5):
                coord = Coordinate(x, y, 0)
                # (0, 1) を壁にする
                terrain = TerrainType.wall() if (x == 0 and y == 1) else TerrainType.grass()
                tiles[coord] = Tile(coord, terrain)
        
        phys_map = PhysicalMapAggregate(
            spot_id=SpotId(spot_id),
            tiles=tiles,
            objects=[self._create_player_object(player_id, 0, 0)]
        )
        phys_repo.save(phys_map)
        
        with pytest.raises(PathBlockedException):
            service.move_tile(MoveTileCommand(player_id=player_id, direction=DirectionEnum.SOUTH))

    def test_actor_busy_exception(self, setup_service):
        """ビジー状態のときに ActorBusyException が発生すること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, _, _, time_provider, _ = setup_service
        
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))
        
        # 1回目の移動
        service.move_tile(MoveTileCommand(player_id=player_id, direction=DirectionEnum.SOUTH))
        
        # ティックが進む前に2回目の移動を試みる
        with pytest.raises(ActorBusyException):
            service.move_tile(MoveTileCommand(player_id=player_id, direction=DirectionEnum.SOUTH))

    def test_domain_exception_converted_to_movement_command_exception(self, setup_service):
        """ドメイン例外が発生した場合、MovementCommandException に変換されて投げられること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))
        self._register_spots(spot_repo, [{"id": spot_id, "name": "S1"}])

        with patch.object(
            phys_repo,
            "find_by_spot_id",
            side_effect=DomainException("test domain error"),
        ):
            with pytest.raises(MovementCommandException) as exc_info:
                service.move_tile(MoveTileCommand(player_id=player_id, direction=DirectionEnum.SOUTH))
            assert "test domain error" in str(exc_info.value)

    def test_unexpected_exception_converted_to_world_system_error(self, setup_service):
        """操作中に想定外の例外が発生した場合は WorldSystemErrorException が投げられること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))
        self._register_spots(spot_repo, [{"id": spot_id, "name": "S1"}])

        with patch.object(
            phys_repo,
            "find_by_spot_id",
            side_effect=RuntimeError("unexpected"),
        ):
            with pytest.raises(WorldSystemErrorException) as exc_info:
                service.move_tile(MoveTileCommand(player_id=player_id, direction=DirectionEnum.SOUTH))
            assert exc_info.value.original_exception is not None
            assert isinstance(exc_info.value.original_exception, RuntimeError)

    def test_get_player_location_profile_missing_raises_player_not_found(self, setup_service):
        """get_player_location でプロフィールが存在しない場合に PlayerNotFoundException が発生すること"""
        service, world_query_service, status_repo, _, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot_id = 1
        # プロフィールは保存しない
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))
        self._register_spots(spot_repo, [{"id": spot_id, "name": "S1"}])

        with pytest.raises(PlayerNotFoundException):
            world_query_service.get_player_location(GetPlayerLocationQuery(player_id=player_id))

    def test_get_player_location_spot_missing_raises_map_not_found(self, setup_service):
        """get_player_location でスポットが存在しない場合に MapNotFoundException が発生すること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot_id = 999  # 物理マップには存在するが SpotRepository に未登録
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))
        # spot_repo には spot_id を登録しない

        with pytest.raises(MapNotFoundException):
            world_query_service.get_player_location(GetPlayerLocationQuery(player_id=player_id))

    def test_get_player_location_unexpected_exception_raises_world_system_error(self, setup_service):
        """get_player_location 内で想定外の例外が発生した場合は WorldSystemErrorException が投げられること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))
        self._register_spots(spot_repo, [{"id": spot_id, "name": "S1"}])

        with patch.object(
            spot_repo,
            "find_by_id",
            side_effect=RuntimeError("unexpected in get_player_location"),
        ):
            with pytest.raises(WorldSystemErrorException) as exc_info:
                world_query_service.get_player_location(GetPlayerLocationQuery(player_id=player_id))
            assert exc_info.value.original_exception is not None
            assert isinstance(exc_info.value.original_exception, RuntimeError)

    def test_location_area_retrieval(self, setup_service):
        """ロケーションエリア内にいる場合、その情報が取得できること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service
        
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 2, 2))
        
        # ロケーションエリアの設定
        location = LocationArea(
            location_id=LocationAreaId(10),
            name="Town Square",
            description="A busy place",
            area=RectArea.from_coordinates(Coordinate(1, 1, 0), Coordinate(3, 3, 0))
        )
        
        phys_map = self._create_sample_map(spot_id, objects=[self._create_player_object(player_id, 2, 2)])
        phys_map.add_location_area(location)
        phys_repo.save(phys_map)
        
        loc_dto = world_query_service.get_player_location(GetPlayerLocationQuery(player_id=player_id))

        assert loc_dto.area_id == 10
        assert loc_dto.area_name == "Town Square"

    def test_multi_hop_destination_and_movement(self, setup_service):
        """複数スポットを跨ぐ移動のテスト"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, _, time_provider, _ = setup_service

        player_id = 1
        spot1_id = 1
        spot2_id = 2
        spot3_id = 3

        gw1to2 = Gateway(
            GatewayId(101), "To Spot 2",
            RectArea.from_coordinates(Coordinate(5, 5, 0), Coordinate(5, 5, 0)),
            SpotId(spot2_id), Coordinate(0, 0, 0)
        )
        gw2to3 = Gateway(
            GatewayId(102), "To Spot 3",
            RectArea.from_coordinates(Coordinate(5, 5, 0), Coordinate(5, 5, 0)),
            SpotId(spot3_id), Coordinate(0, 0, 0)
        )

        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot1_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot1_id, objects=[self._create_player_object(player_id)], gateways=[gw1to2]))
        phys_repo.save(self._create_sample_map(spot2_id, gateways=[gw2to3]))
        phys_repo.save(self._create_sample_map(spot3_id))
        self._register_spots(spot_repo, [{"id": spot1_id, "name": "S1"}, {"id": spot2_id, "name": "S2"}, {"id": spot3_id, "name": "S3"}])
        
        # 目的地を Spot3 に設定（2ホップ先・スポット指定）
        service.set_destination(SetDestinationCommand(player_id=player_id, destination_type="spot", target_spot_id=spot3_id))
        
        updated_status = status_repo.find_by_id(PlayerId(player_id))
        # 最初の暫定目的地は Spot2 へのゲートウェイであるべき
        assert updated_status.current_destination == Coordinate(5, 5, 0)
        
        # ゲートウェイまで移動しきると Spot2 へ遷移するはず
        # ここではモック的に最後の1ステップを実行
        phys_map_spot1 = phys_repo.find_by_spot_id(SpotId(spot1_id))
        phys_map_spot1.move_object(WorldObjectId.create(player_id), Coordinate(5, 5, 0), WorldTick(100))
        phys_repo.save(phys_map_spot1)
        
        updated_status.update_location(SpotId(spot1_id), Coordinate(5, 5, 0))
        status_repo.save(updated_status)
        
        # 時間を進める（移動ビジーを解消するため）
        time_provider.advance_tick(10)
        
        # 次の tick_movement で Spot2 へ遷移
        result = service.tick_movement(TickMovementCommand(player_id=player_id))
        assert result.success is True
        assert result.to_spot_id == spot2_id
        assert result.message == "マップを移動しました"

    def test_map_transition_failure_rollbacks(self, setup_service):
        """遷移先マップが見つからない場合にロールバックされること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, uow, _, _ = setup_service

        player_id = 1
        spot1_id = 1
        spot2_id = 999  # 存在しないマップ（物理マップ未登録）

        gw = Gateway(
            GatewayId(101), "To Nowhere",
            RectArea.from_coordinates(Coordinate(1, 0, 0), Coordinate(1, 0, 0)),
            SpotId(spot2_id), Coordinate(0, 0, 0)
        )

        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id, spot1_id, 0, 0)
        initial_stamina = status.stamina.value
        status_repo.save(status)
        phys_repo.save(self._create_sample_map(spot1_id, objects=[self._create_player_object(player_id)], gateways=[gw]))
        self._register_spots(spot_repo, [{"id": spot1_id, "name": "S1"}, {"id": spot2_id, "name": "S2"}])
        
        # 移動実行
        with pytest.raises(MapNotFoundException):
            service.move_tile(MoveTileCommand(player_id=player_id, direction=DirectionEnum.EAST))
            
        # ロールバックの確認
        # 1. スタミナが消費されていないこと
        final_status = status_repo.find_by_id(PlayerId(player_id))
        assert final_status.stamina.value == initial_stamina
        # 2. 座標が変わっていないこと
        assert final_status.current_coordinate == Coordinate(0, 0, 0)

    def test_tick_movement_path_blocked_clears_path(self, setup_service):
        """自動移動中に道が塞がれた場合、経路がクリアされること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        self._register_spots(spot_repo, [{"id": spot_id, "name": "S1"}])

        # ロケーションエリア (2,0) を目標に追加
        location_area = LocationArea(
            location_id=LocationAreaId(20),
            name="Goal",
            description="",
            area=RectArea.from_coordinates(Coordinate(2, 0, 0), Coordinate(2, 0, 0)),
        )
        phys_map = self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)])
        phys_map.add_location_area(location_area)
        phys_repo.save(phys_map)

        # 目的地をロケーション指定で設定
        service.set_destination(SetDestinationCommand(player_id=player_id, destination_type="location", target_spot_id=spot_id, target_location_area_id=20))
        
        # マップを動的に変更して道を塞ぐ (1, 0) を壁にする
        phys_map = phys_repo.find_by_spot_id(SpotId(spot_id))
        phys_map.change_tile_terrain(Coordinate(1, 0, 0), TerrainType.wall())
        phys_repo.save(phys_map)
        
        # tick_movement 実行
        result = service.tick_movement(TickMovementCommand(player_id=player_id))
        assert result.success is False
        assert "は通行できません" in result.error_message
            
        # 経路がクリアされていること
        updated_status = status_repo.find_by_id(PlayerId(player_id))
        assert updated_status.planned_path == []
        assert updated_status.current_destination is None

    def test_missing_profile_raises_exception(self, setup_service):
        """プロフィールがない場合に例外が発生すること"""
        service, world_query_service, status_repo, _, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot_id = 1
        # プロフィールは保存しない
        status_repo.save(self._create_sample_status(player_id, spot_id))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))
        self._register_spots(spot_repo, [{"id": spot_id, "name": "S1"}])
        
        with pytest.raises(PlayerNotFoundException):
            service.move_tile(MoveTileCommand(player_id=player_id, direction=DirectionEnum.SOUTH))

    def test_missing_spot_raises_exception(self, setup_service):
        """スポット情報がない場合に例外が発生すること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, _, _, _ = setup_service

        player_id = 1
        spot_id = 999  # 物理マップには存在するが SpotRepository に未登録のスポット
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))
        # spot_repo には spot_id を登録しない（移動成功後に DTO 作成で MapNotFoundException）

        with pytest.raises(MapNotFoundException):
            service.move_tile(MoveTileCommand(player_id=player_id, direction=DirectionEnum.SOUTH))

    def test_movement_stamina_cost_with_weather(self, setup_service):
        """天候によって移動時のスタミナ消費が変化すること"""
        service, world_query_service, status_repo, profile_repo, phys_repo, spot_repo, uow, _, event_publisher = setup_service

        custom_config = DefaultMovementConfigService(base_stamina_cost=10.0)
        service._movement_step_executor._movement_config_service = custom_config

        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        self._register_spots(spot_repo, [{"id": spot_id, "name": "S1"}])
        
        # 1. 吹雪のマップを作成 (Roadを使用)
        # BLIZZARD multiplier is 1.8. Road cost is 1.0. 
        # Stamina cost = base(10.0) * terrain_mult(1.0) * weather_mult(1.8) = 18.0.
        phys_map = self._create_sample_map(spot_id, objects=[self._create_player_object(player_id, 0, 0)], terrain_type=TerrainType.road())
        phys_map.set_weather(WeatherState(WeatherTypeEnum.BLIZZARD, 1.0))
        phys_repo.save(phys_map)
        
        status = self._create_sample_status(player_id, spot_id, 0, 0)
        initial_stamina = status.stamina.value
        status_repo.save(status)
        
        # 移動
        service.move_tile(MoveTileCommand(player_id=player_id, direction=DirectionEnum.SOUTH))
        
        # スタミナ消費の検証
        updated_status = status_repo.find_by_id(PlayerId(player_id))
        consumed = initial_stamina - updated_status.stamina.value
        assert consumed == 18

        # イベント発行の検証
        events = event_publisher.get_published_events()
        stamina_events = [e for e in events if isinstance(e, PlayerStaminaConsumedEvent)]
        assert len(stamina_events) == 1
        assert stamina_events[0].consumed_amount == 18


class TestSetDestinationCommandValidation:
    """SetDestinationCommand のバリデーション"""

    def test_destination_type_location_requires_positive_target_location_area_id(self):
        """destination_type が location のとき target_location_area_id が正の整数であること"""
        with pytest.raises(ValueError, match="target_location_area_id must be positive"):
            SetDestinationCommand(
                player_id=1,
                destination_type="location",
                target_spot_id=1,
                target_location_area_id=None,
            )
        with pytest.raises(ValueError, match="target_location_area_id must be positive"):
            SetDestinationCommand(
                player_id=1,
                destination_type="location",
                target_spot_id=1,
                target_location_area_id=0,
            )

    def test_destination_type_spot_does_not_require_target_location_area_id(self):
        """destination_type が spot のとき target_location_area_id は不要"""
        cmd = SetDestinationCommand(player_id=1, destination_type="spot", target_spot_id=2)
        assert cmd.destination_type == "spot"
        assert cmd.target_spot_id == 2
        assert cmd.target_location_area_id is None

    def test_destination_type_location_with_valid_target_location_area_id(self):
        """destination_type が location のとき target_location_area_id を指定できる"""
        cmd = SetDestinationCommand(
            player_id=1,
            destination_type="location",
            target_spot_id=1,
            target_location_area_id=10,
        )
        assert cmd.target_location_area_id == 10

    def test_destination_type_object_requires_positive_target_world_object_id(self):
        """destination_type が object のとき target_world_object_id が正の整数であること"""
        with pytest.raises(ValueError, match="target_world_object_id must be positive"):
            SetDestinationCommand(
                player_id=1,
                destination_type="object",
                target_spot_id=1,
                target_world_object_id=None,
            )
        with pytest.raises(ValueError, match="target_world_object_id must be positive"):
            SetDestinationCommand(
                player_id=1,
                destination_type="object",
                target_spot_id=1,
                target_world_object_id=0,
            )

    def test_destination_type_object_with_valid_target_world_object_id(self):
        """destination_type が object のとき target_world_object_id を指定できる"""
        cmd = SetDestinationCommand(
            player_id=1,
            destination_type="object",
            target_spot_id=1,
            target_world_object_id=200,
        )
        assert cmd.target_world_object_id == 200
