"""MovementStepExecutor の単体テスト。正常系・例外系を網羅する。"""

import pytest
from typing import List, Dict, Optional

from ai_rpg_world.application.world.services.movement_step_executor import MovementStepExecutor
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.player_navigation_state import PlayerNavigationState
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import PhysicalMapAggregate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.entity.world_object import WorldObject
from ai_rpg_world.domain.world.entity.world_object_component import ActorComponent
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, DirectionEnum
from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
from ai_rpg_world.application.world.services.transition_condition_evaluator import (
    TransitionConditionEvaluator,
)
from ai_rpg_world.domain.world.value_object.transition_condition import RequireToll, block_if_weather
from ai_rpg_world.application.world.exceptions.command.movement_command_exception import (
    PlayerNotFoundException,
    MapNotFoundException,
    MovementInvalidException,
    PlayerStaminaExhaustedException,
    PathBlockedException,
    ActorBusyException,
)
from ai_rpg_world.domain.world.service.movement_config_service import DefaultMovementConfigService
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import (
    InMemoryPlayerProfileRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_repository import InMemorySpotRepository
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_transition_policy_repository import (
    InMemoryTransitionPolicyRepository,
)
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import InMemoryUnitOfWork
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
    InMemoryGameTimeProvider,
)


class TestMovementStepExecutor:
    """MovementStepExecutor のテスト。"""

    @pytest.fixture
    def setup_executor(self):
        """MovementStepExecutor とテスト用リポジトリを構築する。"""
        data_store = InMemoryDataStore()
        data_store.clear_all()

        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow, data_store=data_store)

        unit_of_work, _ = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow,
            data_store=data_store,
        )

        player_status_repo = InMemoryPlayerStatusRepository(data_store, unit_of_work)
        player_profile_repo = InMemoryPlayerProfileRepository(data_store, unit_of_work)
        physical_map_repo = InMemoryPhysicalMapRepository(data_store, unit_of_work)
        spot_repo = InMemorySpotRepository(data_store, unit_of_work)
        movement_config_service = DefaultMovementConfigService()
        time_provider = InMemoryGameTimeProvider(initial_tick=100)

        executor = MovementStepExecutor(
            player_status_repository=player_status_repo,
            player_profile_repository=player_profile_repo,
            physical_map_repository=physical_map_repo,
            spot_repository=spot_repo,
            movement_config_service=movement_config_service,
            time_provider=time_provider,
            unit_of_work=unit_of_work,
        )

        return (
            executor,
            player_status_repo,
            player_profile_repo,
            physical_map_repo,
            spot_repo,
            unit_of_work,
            time_provider,
        )

    def _create_sample_status(
        self,
        player_id: int,
        spot_id: int = 1,
        x: int = 0,
        y: int = 0,
        stamina_val: int = 100,
        navigation_state: PlayerNavigationState | None = None,
    ) -> PlayerStatusAggregate:
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
            stamina=Stamina.create(stamina_val, stamina_val),
            navigation_state=nav,
        )

    def _create_sample_profile(self, player_id: int, name: str = "TestPlayer"):
        from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
            PlayerProfileAggregate,
        )
        from ai_rpg_world.domain.player.value_object.player_name import PlayerName
        from ai_rpg_world.domain.player.enum.player_enum import Role

        return PlayerProfileAggregate.create(
            player_id=PlayerId(player_id),
            name=PlayerName(name),
            role=Role.CITIZEN,
        )

    def _create_player_object(self, player_id: int, x: int = 0, y: int = 0) -> WorldObject:
        return WorldObject(
            object_id=WorldObjectId.create(player_id),
            coordinate=Coordinate(x, y, 0),
            object_type=ObjectTypeEnum.PLAYER,
            component=ActorComponent(
                direction=DirectionEnum.SOUTH,
                player_id=PlayerId(player_id),
            ),
        )

    def _create_sample_map(
        self,
        spot_id: int,
        width: int = 10,
        height: int = 10,
        objects: Optional[List[WorldObject]] = None,
        gateways: Optional[List] = None,
        terrain_type: Optional[TerrainType] = None,
    ) -> PhysicalMapAggregate:
        tiles = {}
        for x in range(width):
            for y in range(height):
                coord = Coordinate(x, y, 0)
                tiles[coord] = Tile(coord, terrain_type or TerrainType.grass())
        return PhysicalMapAggregate(
            spot_id=SpotId(spot_id),
            tiles=tiles,
            objects=objects or [],
            gateways=gateways or [],
        )

    def _register_spots(self, spot_repo, spots_data: List[Dict]):
        for s in spots_data:
            spot_repo.save(Spot(SpotId(s["id"]), s["name"], s.get("desc", "")))

    # --- 正常系 ---

    def test_execute_movement_step_direction_success(self, setup_executor):
        """方向指定で移動が成功し、座標と DTO が更新される。"""
        exec_, status_repo, profile_repo, phys_repo, spot_repo, uow, _ = setup_executor
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "S1"}])
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(
            self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)])
        )

        with uow:
            result = exec_.execute_movement_step(player_id, direction=DirectionEnum.SOUTH)

        assert result.success is True
        assert "移動しました" in result.message
        updated = status_repo.find_by_id(PlayerId(player_id))
        assert updated.current_coordinate == Coordinate(0, 1, 0)

    def test_execute_movement_step_target_coordinate_success(self, setup_executor):
        """座標指定で移動が成功する。"""
        exec_, status_repo, profile_repo, phys_repo, spot_repo, uow, _ = setup_executor
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "S1"}])
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 1, 1))
        phys_repo.save(
            self._create_sample_map(
                spot_id, objects=[self._create_player_object(player_id, 1, 1)]
            )
        )

        with uow:
            result = exec_.execute_movement_step(
                player_id,
                target_coordinate=Coordinate(2, 1, 0),
            )

        assert result.success is True
        updated = status_repo.find_by_id(PlayerId(player_id))
        assert updated.current_coordinate == Coordinate(2, 1, 0)

    def test_execute_movement_step_with_passed_player_status(self, setup_executor):
        """既に取得済みの player_status を渡した場合も正しく動作する。"""
        exec_, status_repo, profile_repo, phys_repo, spot_repo, uow, _ = setup_executor
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "S1"}])
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id, spot_id, 0, 0)
        status_repo.save(status)
        phys_repo.save(
            self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)])
        )

        with uow:
            result = exec_.execute_movement_step(
                player_id,
                direction=DirectionEnum.EAST,
                player_status=status,
            )

        assert result.success is True
        updated = status_repo.find_by_id(PlayerId(player_id))
        assert updated.current_coordinate == Coordinate(1, 0, 0)

    def test_execute_movement_step_stamina_consumed(self, setup_executor):
        """スタミナが消費される。"""
        exec_, status_repo, profile_repo, phys_repo, spot_repo, uow, _ = setup_executor
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "S1"}])
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id, spot_id, 0, 0, stamina_val=50)
        initial_stamina = status.stamina.value
        status_repo.save(status)
        phys_repo.save(
            self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)])
        )

        with uow:
            exec_.execute_movement_step(player_id, direction=DirectionEnum.SOUTH)

        updated = status_repo.find_by_id(PlayerId(player_id))
        assert updated.stamina.value < initial_stamina

    def test_execute_movement_step_gateway_message_when_crossing_map(self, setup_executor):
        """ゲートウェイを跨ぐ移動では「マップを移動しました」メッセージが返る。"""
        from ai_rpg_world.domain.world.entity.gateway import Gateway
        from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
        from ai_rpg_world.domain.world.value_object.area import RectArea
        from ai_rpg_world.application.world.handlers.gateway_handler import (
            GatewayTriggeredEventHandler,
        )
        from ai_rpg_world.infrastructure.events import EventHandlerComposition, EventHandlerProfile
        from ai_rpg_world.infrastructure.repository.in_memory_monster_aggregate_repository import (
            InMemoryMonsterAggregateRepository,
        )
        from ai_rpg_world.domain.world.service.map_transition_service import MapTransitionService

        data_store = InMemoryDataStore()
        data_store.clear_all()

        def create_uow():
            return InMemoryUnitOfWork(unit_of_work_factory=create_uow, data_store=data_store)

        unit_of_work, event_publisher = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow,
            data_store=data_store,
        )

        status_repo = InMemoryPlayerStatusRepository(data_store, unit_of_work)
        profile_repo = InMemoryPlayerProfileRepository(data_store, unit_of_work)
        phys_repo = InMemoryPhysicalMapRepository(data_store, unit_of_work)
        spot_repo = InMemorySpotRepository(data_store, unit_of_work)
        monster_repo = InMemoryMonsterAggregateRepository(data_store, unit_of_work)
        map_transition = MapTransitionService()

        gateway_handler = GatewayTriggeredEventHandler(
            physical_map_repository=phys_repo,
            player_status_repository=status_repo,
            monster_repository=monster_repo,
            map_transition_service=map_transition,
            unit_of_work=unit_of_work,
            event_publisher=event_publisher,
        )
        composition = EventHandlerComposition(gateway_handler=gateway_handler)
        composition.register_for_profile(event_publisher, EventHandlerProfile.MOVEMENT_ONLY)

        spot_repo.save(Spot(SpotId(1), "S1", ""))
        spot_repo.save(Spot(SpotId(2), "S2", ""))

        gateway = Gateway(
            gateway_id=GatewayId(1),
            name="To Spot 2",
            area=RectArea.from_coordinates(Coordinate(0, 1, 0), Coordinate(0, 1, 0)),
            target_spot_id=SpotId(2),
            landing_coordinate=Coordinate(0, 0, 0),
        )
        phys_map1 = self._create_sample_map(
            1, objects=[self._create_player_object(1, 0, 0)], gateways=[gateway]
        )
        phys_repo.save(phys_map1)

        tiles2 = {}
        for x in range(5):
            for y in range(5):
                tiles2[Coordinate(x, y, 0)] = Tile(
                    Coordinate(x, y, 0), TerrainType.grass()
                )
        phys_map2 = PhysicalMapAggregate(
            spot_id=SpotId(2),
            tiles=tiles2,
            objects=[],
            gateways=[],
        )
        phys_repo.save(phys_map2)

        profile_repo.save(self._create_sample_profile(1))
        status_repo.save(self._create_sample_status(1, 1, 0, 0))

        exec_ = MovementStepExecutor(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
            movement_config_service=DefaultMovementConfigService(),
            time_provider=InMemoryGameTimeProvider(initial_tick=100),
            unit_of_work=unit_of_work,
        )

        with unit_of_work:
            result = exec_.execute_movement_step(1, direction=DirectionEnum.SOUTH)

        assert result.success is True
        assert "マップを移動しました" in result.message

    # --- 例外系 ---

    def test_execute_movement_step_player_not_found_raises(self, setup_executor):
        """プレイヤーが存在しない場合に PlayerNotFoundException を送出する。"""
        exec_, status_repo, _, phys_repo, spot_repo, uow, _ = setup_executor
        self._register_spots(spot_repo, [{"id": 1, "name": "S1"}])

        with uow:
            with pytest.raises(PlayerNotFoundException):
                exec_.execute_movement_step(999, direction=DirectionEnum.SOUTH)

    def test_execute_movement_step_map_not_found_raises(self, setup_executor):
        """マップが存在しない場合に MapNotFoundException を送出する。"""
        exec_, status_repo, profile_repo, phys_repo, spot_repo, uow, _ = setup_executor
        player_id = 1
        spot_id = 999

        self._register_spots(spot_repo, [{"id": spot_id, "name": "S999"}])
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        # phys_repo には spot_id のマップを登録しない

        with uow:
            with pytest.raises(MapNotFoundException):
                exec_.execute_movement_step(player_id, direction=DirectionEnum.SOUTH)

    def test_execute_movement_step_cannot_act_returns_failure_dto(self, setup_executor):
        """戦闘不能などで can_act() が False のとき失敗 DTO を返す。"""
        exec_, status_repo, profile_repo, phys_repo, spot_repo, uow, _ = setup_executor
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "S1"}])
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id, spot_id, 0, 0)
        status.apply_damage(1000)
        status_repo.save(status)
        phys_repo.save(
            self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)])
        )

        with uow:
            result = exec_.execute_movement_step(player_id, direction=DirectionEnum.SOUTH)

        assert result.success is False
        assert "行動できません" in (result.error_message or "")

    def test_execute_movement_step_no_spot_raises(self, setup_executor):
        """current_spot_id が None のとき MovementInvalidException を送出する。"""
        exec_, status_repo, profile_repo, phys_repo, spot_repo, uow, _ = setup_executor
        player_id = 1

        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(
            1, 1, 0, 0, navigation_state=PlayerNavigationState.empty()
        )
        status_repo.save(status)

        with uow:
            with pytest.raises(MovementInvalidException, match="not on any map"):
                exec_.execute_movement_step(player_id, direction=DirectionEnum.SOUTH)

    def test_execute_movement_step_player_object_missing_raises(self, setup_executor):
        """物理マップにプレイヤーオブジェクトがない場合 MovementInvalidException を送出する。"""
        exec_, status_repo, profile_repo, phys_repo, spot_repo, uow, _ = setup_executor
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "S1"}])
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(self._create_sample_map(spot_id, objects=[]))

        with uow:
            with pytest.raises(MovementInvalidException, match="not found in physical map"):
                exec_.execute_movement_step(player_id, direction=DirectionEnum.SOUTH)

    def test_execute_movement_step_no_direction_or_target_raises(self, setup_executor):
        """方向も座標も指定しない場合 MovementInvalidException を送出する。"""
        exec_, status_repo, profile_repo, phys_repo, spot_repo, uow, _ = setup_executor
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "S1"}])
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(
            self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)])
        )

        with uow:
            with pytest.raises(MovementInvalidException, match="No movement target"):
                exec_.execute_movement_step(player_id)

    def test_execute_movement_step_stamina_exhausted_raises(self, setup_executor):
        """スタミナ不足の場合 PlayerStaminaExhaustedException を送出する。"""
        exec_, status_repo, profile_repo, phys_repo, spot_repo, uow, _ = setup_executor
        player_id = 1
        spot_id = 1

        exec_._movement_config_service = DefaultMovementConfigService(base_stamina_cost=100.0)

        self._register_spots(spot_repo, [{"id": spot_id, "name": "S1"}])
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0, stamina_val=5))
        phys_repo.save(
            self._create_sample_map(spot_id, objects=[self._create_player_object(player_id)])
        )

        with uow:
            with pytest.raises(PlayerStaminaExhaustedException):
                exec_.execute_movement_step(player_id, direction=DirectionEnum.SOUTH)

    def test_execute_movement_step_wall_blocked_raises_path_blocked(self, setup_executor):
        """壁への移動で PathBlockedException を送出する。"""
        exec_, status_repo, profile_repo, phys_repo, spot_repo, uow, _ = setup_executor
        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "S1"}])
        profile_repo.save(self._create_sample_profile(player_id))
        status_repo.save(self._create_sample_status(player_id, spot_id, 0, 0))
        phys_repo.save(
            self._create_sample_map(
                spot_id,
                objects=[self._create_player_object(player_id)],
                terrain_type=TerrainType.grass(),
            )
        )
        phys_map = phys_repo.find_by_spot_id(SpotId(spot_id))
        for coord in [Coordinate(0, 1, 0)]:
            phys_map._tiles[coord] = Tile(coord, TerrainType.wall())
        phys_repo.save(phys_map)

        with uow:
            with pytest.raises(PathBlockedException):
                exec_.execute_movement_step(player_id, direction=DirectionEnum.SOUTH)

    def test_execute_movement_step_gateway_blocked_by_toll_returns_failure_dto(
        self, setup_executor
    ):
        """ゲートウェイが通行料でブロックされているとき失敗 DTO を返す。"""
        from ai_rpg_world.domain.world.entity.gateway import Gateway
        from ai_rpg_world.domain.world.value_object.gateway_id import GatewayId
        from ai_rpg_world.domain.world.value_object.area import RectArea

        exec_, status_repo, profile_repo, phys_repo, spot_repo, uow, _ = setup_executor
        policy_repo = InMemoryTransitionPolicyRepository()
        policy_repo.set_conditions(
            SpotId(1),
            SpotId(2),
            [RequireToll(amount_gold=1000)],
        )
        evaluator = TransitionConditionEvaluator()

        executor_with_policy = MovementStepExecutor(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
            movement_config_service=DefaultMovementConfigService(),
            time_provider=InMemoryGameTimeProvider(initial_tick=100),
            unit_of_work=uow,
            transition_policy_repository=policy_repo,
            transition_condition_evaluator=evaluator,
        )

        player_id = 1
        spot_id = 1

        self._register_spots(spot_repo, [{"id": spot_id, "name": "S1"}])
        profile_repo.save(self._create_sample_profile(player_id))
        status = self._create_sample_status(player_id, spot_id, 0, 0)
        status._gold = type(status._gold).create(10)
        status_repo.save(status)

        gateway = Gateway(
            gateway_id=GatewayId(1),
            name="To Spot 2",
            area=RectArea.from_coordinates(Coordinate(0, 1, 0), Coordinate(0, 1, 0)),
            target_spot_id=SpotId(2),
            landing_coordinate=Coordinate(0, 0, 0),
        )
        phys_repo.save(
            self._create_sample_map(
                1,
                objects=[self._create_player_object(player_id)],
                gateways=[gateway],
            )
        )

        with uow:
            result = executor_with_policy.execute_movement_step(
                player_id, direction=DirectionEnum.SOUTH
            )

        assert result.success is False
        assert "通行料" in (result.error_message or "") or "不足" in (result.error_message or "")
