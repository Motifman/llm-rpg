import pytest
from datetime import datetime
from typing import List, Dict

from ai_rpg_world.application.world.services.movement_service import MovementApplicationService
from ai_rpg_world.application.world.contracts.commands import (
    MoveTileCommand,
    SetDestinationCommand,
    TickMovementCommand,
    GetPlayerLocationCommand
)
from ai_rpg_world.domain.world.entity.location_area import LocationArea
from ai_rpg_world.domain.world.value_object.location_area_id import LocationAreaId
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    PlayerNotFoundException,
    MapNotFoundException,
    MovementInvalidException,
    PlayerStaminaExhaustedException,
    PathBlockedException,
    ActorBusyException
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
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
from ai_rpg_world.domain.world.aggregate.world_map_aggregate import WorldMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.world_id import WorldId
from ai_rpg_world.domain.world.value_object.connection import Connection
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
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
from ai_rpg_world.domain.world.service.map_transition_service import MapTransitionService
from ai_rpg_world.domain.world.service.global_pathfinding_service import GlobalPathfindingService
from ai_rpg_world.domain.world.service.movement_config_service import DefaultMovementConfigService
from ai_rpg_world.domain.player.event.status_events import PlayerLocationChangedEvent, PlayerStaminaConsumedEvent
from ai_rpg_world.domain.world.event.map_events import WorldObjectMovedEvent, GatewayTriggeredEvent
from ai_rpg_world.application.world.handlers.gateway_handler import GatewayTriggeredEventHandler
from ai_rpg_world.infrastructure.world.pathfinding.astar_pathfinding_strategy import AStarPathfindingStrategy
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import InMemoryPlayerStatusRepository
from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import InMemoryPlayerProfileRepository
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import InMemoryPhysicalMapRepository
from ai_rpg_world.infrastructure.repository.in_memory_world_map_repository import InMemoryWorldMapRepository
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
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
        world_map_repo = InMemoryWorldMapRepository(data_store, unit_of_work)
        
        pathfinding_service = PathfindingService(AStarPathfindingStrategy())
        global_pathfinding_service = GlobalPathfindingService(pathfinding_service)
        movement_config_service = DefaultMovementConfigService()
        map_transition_service = MapTransitionService()
        time_provider = InMemoryGameTimeProvider(initial_tick=100)
        
        # 同期イベントハンドラの登録
        gateway_handler = GatewayTriggeredEventHandler(
            physical_map_repository=physical_map_repo,
            player_status_repository=player_status_repo,
            map_transition_service=map_transition_service,
            event_publisher=event_publisher
        )
        event_publisher.register_handler(GatewayTriggeredEvent, gateway_handler, is_synchronous=True)

        service = MovementApplicationService(
            player_status_repository=player_status_repo,
            player_profile_repository=player_profile_repo,
            physical_map_repository=physical_map_repo,
            world_map_repository=world_map_repo,
            global_pathfinding_service=global_pathfinding_service,
            movement_config_service=movement_config_service,
            time_provider=time_provider,
            unit_of_work=unit_of_work
        )
        
        # デフォルトのスポットを登録しておく
        world_map = WorldMapAggregate(WorldId(1), spots=[Spot(SpotId(1), "Default Spot", "")])
        world_map_repo.save(world_map)
        
        return service, player_status_repo, player_profile_repo, physical_map_repo, world_map_repo, unit_of_work, time_provider, event_publisher

    def _create_sample_status(self, player_id: int, spot_id: int = 1, x: int = 0, y: int = 0):
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
            current_spot_id=SpotId(spot_id),
            current_coordinate=Coordinate(x, y, 0)
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

    def _create_world_map(self, world_id_val: int, spots_data: List[Dict]):
        spots = [Spot(SpotId(s["id"]), s["name"], s.get("desc", "")) for s in spots_data]
        return WorldMapAggregate(WorldId(world_id_val), spots=spots)

    def _create_player_object(self, player_id: int, x: int = 0, y: int = 0):
        return WorldObject(
            object_id=WorldObjectId.create(player_id),
            coordinate=Coordinate(x, y, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(direction=DirectionEnum.SOUTH)
        )

    def test_move_tile_success_and_dto_completeness(self, setup_service):
        """タイルベースの移動が成功し、DTOが完全に埋まっていること"""
        service, status_repo, profile_repo, phys_repo, world_repo, uow, _, event_publisher = setup_service
        
        player_id = 1
        spot_id = 1
        # プロフィールとワールドマップの準備
        profile = self._create_sample_profile(player_id, "Alice")
        profile_repo.save(profile)
        
        world_map = self._create_world_map(1, [{"id": spot_id, "name": "Starting Village"}])
        world_repo.save(world_map)
        
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

    def test_find_correct_world_map(self, setup_service):
        """複数の世界地図がある場合、正しい世界地図が選択されること"""
        service, status_repo, profile_repo, phys_repo, world_repo, _, _, _ = setup_service
        
        player_id = 1
        spot1_id = 101
        spot2_id = 201
        
        # 2つの世界地図を作成
        world1 = self._create_world_map(1, [{"id": spot1_id, "name": "World 1 Spot"}])
        world2 = self._create_world_map(2, [{"id": spot2_id, "name": "World 2 Spot"}])
        world_repo.save(world1)
        world_repo.save(world2)
        
        # プレイヤーをWorld 2のスポットに配置
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot2_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot2_id, objects=[self._create_player_object(player_id)]))
        
        # 目的地を同じWorld 2内の別の座標に設定
        command = SetDestinationCommand(player_id=player_id, target_spot_id=spot2_id, target_x=1, target_y=1)
        result = service.set_destination(command)
        
        assert result.success is True
        assert result.to_spot_id == spot2_id

    def test_set_destination_player_not_on_map(self, setup_service):
        """プレイヤーがどのマップにも配置されていない場合、エラーになること"""
        service, status_repo, profile_repo, _, _, _, _, _ = setup_service
        
        player_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        # current_spot_id を None にする
        status = self._create_sample_status(player_id)
        status._current_spot_id = None
        status_repo.save(status)
        
        command = SetDestinationCommand(player_id=player_id, target_spot_id=1, target_x=1, target_y=1)
        with pytest.raises(MovementInvalidException, match="not placed on any map"):
            service.set_destination(command)

    def test_move_tile_player_object_missing_from_map(self, setup_service):
        """プレイヤー状態はあるが物理マップ上にオブジェクトがない場合、エラーになること"""
        service, status_repo, profile_repo, phys_repo, world_repo, _, _, _ = setup_service
        
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
        service, status_repo, profile_repo, phys_repo, world_repo, _, _, _ = setup_service
        
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
        service, status_repo, profile_repo, phys_repo, world_repo, _, _, _ = setup_service
        
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id, "Charlie"))
        status = self._create_sample_status(player_id, spot_id, 0, 0)
        # 予め経路を設定しておくが、わざと行き止まりにする
        status.set_destination(Coordinate(1, 0, 0), [Coordinate(0, 0, 0), Coordinate(1, 0, 0)])
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
        service, status_repo, profile_repo, phys_repo, world_repo, _, time_provider, _ = setup_service
        
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
        service, status_repo, profile_repo, phys_repo, world_repo, _, time_provider, _ = setup_service
        
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id, spot_id, 0, 0)
        status_repo.save(status)
        
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))
        
        # ワールドマップ情報が必要
        world_repo.save(self._create_world_map(1, [{"id": spot_id, "name": "Spot 1"}]))
        
        # 目的地を設定
        service.set_destination(SetDestinationCommand(player_id=player_id, target_spot_id=spot_id, target_x=2, target_y=0))
        
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

    def test_gateway_transition_uses_service(self, setup_service):
        """ゲートウェイ移動がドメインサービスを通じて正しく処理されること"""
        service, status_repo, profile_repo, phys_repo, world_repo, _, _, _ = setup_service
        
        player_id = 1
        spot1_id = 1
        spot2_id = 2
        
        # ゲートウェイ設置
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
        phys_repo.save(self._create_sample_map(spot2_id)) # 移動先マップ
        
        # ワールドマップ情報
        world_repo.save(self._create_world_map(1, [{"id": spot1_id, "name": "Spot 1"}, {"id": spot2_id, "name": "Spot 2"}]))
        
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

    def test_domain_exception_handling(self, setup_service):
        """ドメイン例外が適切にキャッチされ、失敗DTOとして返されること"""
        service, status_repo, profile_repo, phys_repo, _, _, _, _ = setup_service
        
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
        service, status_repo, profile_repo, phys_repo, world_repo, _, _, _ = setup_service
        
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id, "Bob"))
        status_repo.save(self._create_sample_status(player_id, spot_id, 3, 4))
        
        world_repo.save(self._create_world_map(1, [{"id": spot_id, "name": "Secret Base", "desc": "Hidden location"}]))
        
        loc = service.get_player_location(GetPlayerLocationCommand(player_id=player_id))
        
        assert loc is not None
        assert loc.player_name == "Bob"
        assert loc.current_spot_name == "Secret Base"
        assert loc.current_spot_description == "Hidden location"
        assert loc.x == 3
        assert loc.y == 4

    def test_multi_spot_pathfinding_initial_step(self, setup_service):
        """スポットを跨ぐ目的地設定時に、まずゲートウェイを目指すパスが生成されること"""
        service, status_repo, profile_repo, phys_repo, world_repo, _, _, _ = setup_service
        
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
        
        # ワールドマップ情報
        world_repo.save(self._create_world_map(1, [{"id": spot1_id, "name": "Spot 1"}, {"id": spot2_id, "name": "Spot 2"}]))
        
        # 別スポットを目的地に設定
        service.set_destination(SetDestinationCommand(player_id=player_id, target_spot_id=spot2_id, target_x=10, target_y=10))
        
        updated_status = status_repo.find_by_id(PlayerId(player_id))
        # 目的地がゲートウェイの座標になっていること
        assert updated_status.current_destination == Coordinate(5, 0, 0)
        # パスが生成されていること
        assert len(updated_status.planned_path) > 1

    def test_player_not_found(self, setup_service):
        """存在しないプレイヤーを指定した場合に PlayerNotFoundException が発生すること"""
        service, _, _, _, _, _, _, _ = setup_service
        
        with pytest.raises(PlayerNotFoundException):
            service.move_tile(MoveTileCommand(player_id=999, direction=DirectionEnum.NORTH))

    def test_map_not_found(self, setup_service):
        """プレイヤーがいるはずのマップが存在しない場合に MapNotFoundException が発生すること"""
        service, status_repo, profile_repo, _, _, _, _, _ = setup_service
        
        player_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        # マップID 999 にプレイヤーを配置するが、その物理マップは作成しない
        status_repo.save(self._create_sample_status(player_id, spot_id=999, x=0, y=0))
        
        with pytest.raises(MapNotFoundException):
            service.move_tile(MoveTileCommand(player_id=player_id, direction=DirectionEnum.NORTH))

    def test_stamina_exhaustion(self, setup_service):
        """スタミナ不足時に PlayerStaminaExhaustedException が発生すること"""
        service, status_repo, profile_repo, phys_repo, _, _, _, _ = setup_service
        
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
        service, status_repo, profile_repo, phys_repo, _, _, _, _ = setup_service
        
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
        service, status_repo, profile_repo, phys_repo, _, _, time_provider, _ = setup_service
        
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

    def test_location_area_retrieval(self, setup_service):
        """ロケーションエリア内にいる場合、その情報が取得できること"""
        service, status_repo, profile_repo, phys_repo, world_repo, _, _, _ = setup_service
        
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
        
        loc_dto = service.get_player_location(GetPlayerLocationCommand(player_id=player_id))
        
        assert loc_dto.area_id == 10
        assert loc_dto.area_name == "Town Square"

    def test_multi_hop_destination_and_movement(self, setup_service):
        """複数スポットを跨ぐ移動のテスト"""
        service, status_repo, profile_repo, phys_repo, world_repo, _, time_provider, _ = setup_service
        
        player_id = 1
        spot1_id = 1
        spot2_id = 2
        spot3_id = 3
        
        # Spot1 -> Spot2 へのゲートウェイ
        gw1to2 = Gateway(
            GatewayId(101), "To Spot 2", 
            RectArea.from_coordinates(Coordinate(5, 5, 0), Coordinate(5, 5, 0)),
            SpotId(spot2_id), Coordinate(0, 0, 0)
        )
        
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot1_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot1_id, objects=[self._create_player_object(player_id)], gateways=[gw1to2]))
        phys_repo.save(self._create_sample_map(spot2_id)) # Spot2
        phys_repo.save(self._create_sample_map(spot3_id)) # Spot3
        
        # ワールドマップ接続: 1 -> 2 -> 3
        world_map = WorldMapAggregate(
            WorldId(1), 
            spots=[
                Spot(SpotId(spot1_id), "S1", ""), 
                Spot(SpotId(spot2_id), "S2", ""), 
                Spot(SpotId(spot3_id), "S3", "")
            ]
        )
        world_map.add_connection(Connection(SpotId(spot1_id), SpotId(spot2_id)))
        world_map.add_connection(Connection(SpotId(spot2_id), SpotId(spot3_id)))
        world_repo.save(world_map)
        
        # 目的地を Spot3 に設定（2ホップ先）
        service.set_destination(SetDestinationCommand(player_id=player_id, target_spot_id=spot3_id, target_x=10, target_y=10))
        
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
        service, status_repo, profile_repo, phys_repo, world_repo, uow, _, _ = setup_service
        
        player_id = 1
        spot1_id = 1
        spot2_id = 999 # 存在しないマップ
        
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
        
        # ワールドマップには登録しておく
        world_repo.save(self._create_world_map(1, [{"id": spot1_id, "name": "S1"}, {"id": spot2_id, "name": "S2"}]))
        
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
        service, status_repo, profile_repo, phys_repo, world_repo, _, _, _ = setup_service
        
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        world_repo.save(self._create_world_map(1, [{"id": spot_id, "name": "S1"}]))
        
        # マップ作成。 (1, 0) は通れる状態
        phys_map = self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)])
        phys_repo.save(phys_map)
        
        # 目的地設定
        service.set_destination(SetDestinationCommand(player_id=player_id, target_spot_id=spot_id, target_x=2, target_y=0))
        
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
        service, status_repo, _, phys_repo, world_repo, _, _, _ = setup_service
        
        player_id = 1
        spot_id = 1
        # プロフィールは保存しない
        status_repo.save(self._create_sample_status(player_id, spot_id))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))
        world_repo.save(self._create_world_map(1, [{"id": spot_id, "name": "S1"}]))
        
        with pytest.raises(PlayerNotFoundException):
            service.move_tile(MoveTileCommand(player_id=player_id, direction=DirectionEnum.SOUTH))

    def test_missing_spot_raises_exception(self, setup_service):
        """スポット情報がない場合に例外が発生すること"""
        service, status_repo, profile_repo, phys_repo, world_repo, _, _, _ = setup_service
        
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id))
        phys_repo.save(self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)]))
        # ワールドマップにスポットを登録しない
        world_repo.save(self._create_world_map(1, []))
        
        with pytest.raises(MapNotFoundException):
            service.move_tile(MoveTileCommand(player_id=player_id, direction=DirectionEnum.SOUTH))

    def test_movement_stamina_cost_with_weather(self, setup_service):
        """天候によって移動時のスタミナ消費が変化すること"""
        service, status_repo, profile_repo, phys_repo, world_repo, uow, _, event_publisher = setup_service
        
        # スタミナ基本消費を10に設定
        service._movement_config_service = DefaultMovementConfigService(base_stamina_cost=10.0)
        
        player_id = 1
        spot_id = 1
        profile_repo.save(self._create_sample_profile(player_id))
        world_repo.save(self._create_world_map(1, [{"id": spot_id, "name": "S1"}]))
        
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
