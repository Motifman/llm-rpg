import pytest
import unittest.mock as mock
from types import SimpleNamespace
from ai_rpg_world.application.world.services.world_simulation_service import WorldSimulationApplicationService
from ai_rpg_world.application.world.services.caching_pathfinding_service import CachingPathfindingService
from ai_rpg_world.application.world.services.pursuit_continuation_service import (
    PursuitContinuationAction,
    PursuitContinuationDecision,
    PursuitContinuationService,
)
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
from ai_rpg_world.domain.monster.enum.monster_enum import ActiveTimeType
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
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
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
from ai_rpg_world.domain.world.enum.world_enum import ObjectTypeEnum, DirectionEnum, BehaviorActionType
from ai_rpg_world.domain.monster.enum.monster_enum import BehaviorStateEnum
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
from ai_rpg_world.domain.world.entity.world_object_component import AutonomousBehaviorComponent, ActorComponent
from ai_rpg_world.application.harvest.services.harvest_command_service import HarvestCommandService
from ai_rpg_world.domain.world.entity.world_object_component import HarvestableComponent
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import InMemoryItemRepository
from ai_rpg_world.infrastructure.repository.in_memory_loot_table_repository import InMemoryLootTableRepository
from ai_rpg_world.infrastructure.repository.in_memory_item_spec_repository import InMemoryItemSpecRepository
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import InMemoryPlayerInventoryRepository
from ai_rpg_world.domain.world.service.harvest_domain_service import HarvestDomainService
from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import LootEntry, LootTableAggregate
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.read_model.item_spec_read_model import ItemSpecReadModel
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.world.event.map_events import ResourceHarvestedEvent
from ai_rpg_world.domain.monster.value_object.monster_skill_info import MonsterSkillInfo
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
from ai_rpg_world.domain.monster.event.monster_events import (
    TargetSpottedEvent,
    ActorStateChangedEvent,
)
from ai_rpg_world.domain.world.enum.world_enum import Disposition
from ai_rpg_world.application.world.contracts.dtos import VisibleObjectDto
from ai_rpg_world.domain.pursuit.enum.pursuit_failure_reason import (
    PursuitFailureReason,
)
from ai_rpg_world.domain.pursuit.event.pursuit_events import PursuitFailedEvent
from ai_rpg_world.domain.pursuit.value_object.pursuit_last_known_state import (
    PursuitLastKnownState,
)
from ai_rpg_world.domain.pursuit.value_object.pursuit_state import PursuitState
from ai_rpg_world.domain.pursuit.value_object.pursuit_target_snapshot import (
    PursuitTargetSnapshot,
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
    @staticmethod
    def _player_status(player_id: int = 1) -> PlayerStatusAggregate:
        return PlayerStatusAggregate(
            player_id=PlayerId(player_id),
            base_stats=BaseStats(10, 10, 10, 10, 10, 0.05, 0.05),
            stat_growth_factor=StatGrowthFactor(1.1, 1.1, 1.1, 1.1, 1.1, 0.01, 0.01),
            exp_table=ExpTable(100, 1.5),
            growth=Growth(1, 0, ExpTable(100, 1.5)),
            gold=Gold(0),
            hp=Hp.create(100, 100),
            mp=Mp.create(30, 30),
            stamina=Stamina.create(100, 100),
            current_spot_id=SpotId(1),
            current_coordinate=Coordinate(0, 0, 0),
        )

    @staticmethod
    def _player_actor(player_id: int = 1, *, busy_until=None) -> WorldObject:
        return WorldObject(
            WorldObjectId(player_id),
            Coordinate(0, 0, 0),
            ObjectTypeEnum.PLAYER,
            component=ActorComponent(
                direction=DirectionEnum.EAST,
                player_id=PlayerId(player_id),
            ),
            busy_until=busy_until,
        )

    @staticmethod
    def _current_state(
        *,
        visible_objects: list[VisibleObjectDto],
        current_spot_id: int = 1,
        has_active_path: bool = False,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            visible_objects=visible_objects,
            has_active_path=has_active_path,
            current_spot_id=current_spot_id,
        )

    @staticmethod
    def _visible_target(
        target_id: int,
        *,
        x: int,
        y: int,
        z: int = 0,
        object_kind: str = "monster",
    ) -> VisibleObjectDto:
        return VisibleObjectDto(
            object_id=target_id,
            object_type="actor",
            x=x,
            y=y,
            z=z,
            distance=1,
            display_name=f"target-{target_id}",
            object_kind=object_kind,
        )

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
        behavior_service = BehaviorService()
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
        from ai_rpg_world.domain.world.service.skill_selection_policy import FirstInRangeSkillPolicy
        from ai_rpg_world.application.world.services.monster_action_resolver import create_monster_action_resolver_factory
        from ai_rpg_world.application.world.handlers.monster_decided_to_move_handler import MonsterDecidedToMoveHandler
        from ai_rpg_world.application.world.handlers.monster_decided_to_use_skill_handler import MonsterDecidedToUseSkillHandler
        from ai_rpg_world.application.world.handlers.monster_decided_to_interact_handler import MonsterDecidedToInteractHandler
        from ai_rpg_world.application.world.handlers.monster_fed_handler import MonsterFedHandler
        from ai_rpg_world.infrastructure.events.monster_event_handler_registry import MonsterEventHandlerRegistry

        hit_box_factory = HitBoxFactory()
        monster_action_resolver_factory = create_monster_action_resolver_factory(
            caching_pathfinding,
            FirstInRangeSkillPolicy(),
        )
        monster_decided_to_move_handler = MonsterDecidedToMoveHandler(
            physical_map_repository=repository,
            monster_repository=monster_repo,
        )
        monster_decided_to_use_skill_handler = MonsterDecidedToUseSkillHandler(
            physical_map_repository=repository,
            monster_repository=monster_repo,
            monster_skill_execution_domain_service=monster_skill_execution_domain_service,
            hit_box_factory=hit_box_factory,
            hit_box_repository=hit_box_repo,
            skill_loadout_repository=skill_loadout_repo,
        )
        monster_decided_to_interact_handler = MonsterDecidedToInteractHandler(
            physical_map_repository=repository,
        )
        monster_fed_handler = MonsterFedHandler(monster_repository=monster_repo)
        MonsterEventHandlerRegistry(
            monster_decided_to_move_handler,
            monster_decided_to_use_skill_handler,
            monster_decided_to_interact_handler,
            monster_fed_handler,
        ).register_handlers(event_publisher)

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
            monster_action_resolver_factory=monster_action_resolver_factory,
        )
        
        return service, time_provider, repository, weather_zone_repo, player_status_repo, hit_box_repo, uow, event_publisher, monster_repo, skill_loadout_repo

    def test_tick_advances_time(self, setup_service):
        """tickによってゲーム時間が進むこと"""
        service, time_provider, _, _, _, _, _, _, _, _ = setup_service

        assert time_provider.get_current_tick() == WorldTick(10)

        service.tick()

        assert time_provider.get_current_tick() == WorldTick(11)

    def test_tick_auto_completes_due_player_harvest(self, setup_service):
        service, time_provider, repository, _, player_status_repo, _, uow, event_publisher, _, _ = setup_service
        data_store = repository._data_store
        loot_table_repo = InMemoryLootTableRepository()
        item_repo = InMemoryItemRepository(data_store, uow)
        item_spec_repo = InMemoryItemSpecRepository()
        inventory_repo = InMemoryPlayerInventoryRepository(data_store, uow)
        service._harvest_command_service = HarvestCommandService(
            repository,
            loot_table_repo,
            item_repo,
            item_spec_repo,
            inventory_repo,
            player_status_repo,
            HarvestDomainService(),
            uow,
        )

        player_status_repo.save(self._player_status(1))
        inventory_repo.save(PlayerInventoryAggregate.create_new_inventory(PlayerId(1)))
        item_spec_repo.save(
            ItemSpecReadModel(
                item_spec_id=ItemSpecId(9),
                name="鉄鉱石",
                item_type=ItemType.MATERIAL,
                rarity=Rarity.COMMON,
                description="鉄の素材",
                max_stack_size=MaxStackSize(64),
            )
        )
        loot_table_repo.save(LootTableAggregate.create(1, [LootEntry(ItemSpecId(9), weight=100)]))

        actor = self._player_actor(1, busy_until=WorldTick(11))
        resource = WorldObject(
            WorldObjectId(200),
            Coordinate(1, 0, 0),
            ObjectTypeEnum.RESOURCE,
            component=HarvestableComponent(loot_table_id=1, harvest_duration=1, stamina_cost=1),
        )
        resource.component.start_harvest(WorldObjectId(1), WorldTick(10))
        physical_map = PhysicalMapAggregate.create(
            SpotId(1),
            [
                Tile(Coordinate(0, 0, 0), TerrainType.grass()),
                Tile(Coordinate(1, 0, 0), TerrainType.grass()),
            ],
            objects=[actor, resource],
        )
        repository.save(physical_map)

        service.tick()

        updated_map = repository.find_by_spot_id(SpotId(1))
        assert updated_map.get_object(WorldObjectId(200)).component.current_actor_id is None
        assert updated_map.get_object(WorldObjectId(1)).busy_until is None
        events = event_publisher.get_published_events()
        assert any(isinstance(event, ResourceHarvestedEvent) for event in events)

    def test_tick_calls_llm_turn_trigger_run_scheduled_turns_when_provided(self, setup_service):
        """llm_turn_trigger を渡しているとき、tick の末尾で run_scheduled_turns が 1 回呼ばれる"""
        service, _, _, _, _, _, _, _, _, _ = setup_service
        mock_trigger = mock.MagicMock()
        service._llm_turn_trigger = mock_trigger

        service.tick()

        mock_trigger.run_scheduled_turns.assert_called_once()

    def test_tick_when_llm_turn_trigger_none_does_not_call_run_scheduled_turns(self, setup_service):
        """llm_turn_trigger を渡していない（None）とき、tick 内で run_scheduled_turns は呼ばれない"""
        service, _, _, _, _, _, _, _, _, _ = setup_service
        assert service._llm_turn_trigger is None
        # tick が正常完了すれば、run_scheduled_turns は呼ばれていない（None のため）
        result = service.tick()
        assert result is not None

    def test_tick_when_llm_turn_trigger_run_scheduled_turns_raises_propagates_as_system_error(
        self, setup_service
    ):
        """llm_turn_trigger.run_scheduled_turns が例外を投げた場合、SystemErrorException でラップされて伝播する"""
        service, _, _, _, _, _, _, _, _, _ = setup_service
        mock_trigger = mock.MagicMock()
        mock_trigger.run_scheduled_turns.side_effect = RuntimeError("run_scheduled_turns failed")
        service._llm_turn_trigger = mock_trigger

        with pytest.raises(SystemErrorException, match="tick failed") as exc_info:
            service.tick()

        assert exc_info.value.original_exception is not None
        assert isinstance(exc_info.value.original_exception, RuntimeError)
        assert "run_scheduled_turns failed" in str(exc_info.value.original_exception)
        mock_trigger.run_scheduled_turns.assert_called_once()

    def test_tick_advances_pending_player_movement_when_movement_service_provided(
        self, setup_service
    ):
        service, _, repository, _, player_status_repo, _, _, _, _, _ = setup_service
        status = self._player_status()
        status.set_destination(
            Coordinate(1, 0, 0),
            [Coordinate(0, 0, 0), Coordinate(1, 0, 0)],
            goal_destination_type="spot",
            goal_spot_id=SpotId(1),
        )
        player_status_repo.save(status)

        physical_map = PhysicalMapAggregate.create(
            SpotId(1),
            [Tile(Coordinate(x, y, 0), TerrainType.grass()) for x in range(3) for y in range(3)],
            objects=[self._player_actor()],
        )
        repository.save(physical_map)

        movement_service = mock.MagicMock()
        service._movement_service = movement_service

        service.tick()

        movement_service.tick_movement_in_current_unit_of_work.assert_called_once_with(1)

    def test_pursuit_continuation_marks_pathless_pursuit_for_same_tick_continuation(
        self,
    ):
        status = self._player_status()
        status.start_pursuit(
            PursuitTargetSnapshot(
                target_id=WorldObjectId(99),
                spot_id=SpotId(1),
                coordinate=Coordinate(2, 0, 0),
            )
        )
        movement_service = mock.Mock()
        movement_service.replan_path_to_coordinate_in_current_unit_of_work.return_value = (
            SimpleNamespace(success=True)
        )
        world_query_service = mock.Mock()
        world_query_service.get_player_current_state.return_value = self._current_state(
            visible_objects=[],
            has_active_path=False,
        )
        continuation_service = PursuitContinuationService(
            world_query_service,
            movement_service=movement_service,
        )

        decision = continuation_service.evaluate_tick(status)

        assert decision.continuation_checked is True
        assert decision.action == PursuitContinuationAction.CONTINUE_PURSUIT
        assert decision.should_advance_movement is True
        assert decision.replan_required is True
        assert decision.replan_attempted is True
        assert decision.target_world_object_id == 99
        movement_service.replan_path_to_coordinate_in_current_unit_of_work.assert_called_once()
        world_query_service.get_player_current_state.assert_called_once()

    def test_pursuit_continuation_refreshes_visible_target_only_when_coordinate_changes(
        self,
    ):
        status = self._player_status()
        status.start_pursuit(
            PursuitTargetSnapshot(
                target_id=WorldObjectId(99),
                spot_id=SpotId(1),
                coordinate=Coordinate(2, 0, 0),
            )
        )
        world_query_service = mock.Mock()
        world_query_service.get_player_current_state.side_effect = [
            self._current_state(
                visible_objects=[self._visible_target(99, x=2, y=0)],
                has_active_path=True,
            ),
            self._current_state(
                visible_objects=[self._visible_target(99, x=3, y=0)],
                has_active_path=True,
            ),
        ]
        movement_service = mock.Mock()
        movement_service.replan_path_to_coordinate_in_current_unit_of_work.return_value = (
            SimpleNamespace(success=True)
        )
        continuation_service = PursuitContinuationService(
            world_query_service,
            movement_service=movement_service,
        )

        first = continuation_service.evaluate_tick(status)
        second = continuation_service.evaluate_tick(status)

        assert first.pursuit_updated is False
        assert first.replan_attempted is False
        assert second.pursuit_updated is True
        assert second.replan_attempted is True
        assert status.pursuit_state is not None
        assert status.pursuit_state.target_snapshot.coordinate == Coordinate(3, 0, 0)
        assert status.pursuit_state.last_known.coordinate == Coordinate(3, 0, 0)

    def test_pursuit_continuation_preserves_last_visible_snapshot_when_target_is_lost(
        self,
    ):
        status = self._player_status()
        status.start_pursuit(
            PursuitTargetSnapshot(
                target_id=WorldObjectId(55),
                spot_id=SpotId(1),
                coordinate=Coordinate(4, 1, 0),
            )
        )
        movement_service = mock.Mock()
        movement_service.replan_path_to_coordinate_in_current_unit_of_work.return_value = (
            SimpleNamespace(success=True)
        )
        world_query_service = mock.Mock()
        world_query_service.get_player_current_state.return_value = self._current_state(
            visible_objects=[],
            has_active_path=False,
        )
        continuation_service = PursuitContinuationService(
            world_query_service,
            movement_service=movement_service,
        )

        decision = continuation_service.evaluate_tick(status)

        assert decision.action == PursuitContinuationAction.CONTINUE_PURSUIT
        assert decision.has_visible_target is False
        assert decision.replan_attempted is True
        assert status.pursuit_state is not None
        assert status.pursuit_state.target_snapshot.coordinate == Coordinate(4, 1, 0)
        assert status.pursuit_state.last_known.coordinate == Coordinate(4, 1, 0)

    def test_pursuit_continuation_invisible_target_does_not_become_target_missing(
        self,
    ):
        status = self._player_status()
        status.start_pursuit(
            PursuitTargetSnapshot(
                target_id=WorldObjectId(66),
                spot_id=SpotId(1),
                coordinate=Coordinate(4, 1, 0),
            )
        )
        movement_service = mock.Mock()
        movement_service.replan_path_to_coordinate_in_current_unit_of_work.return_value = (
            SimpleNamespace(success=True)
        )
        world_query_service = mock.Mock()
        world_query_service.get_player_current_state.return_value = self._current_state(
            visible_objects=[],
            has_active_path=False,
        )
        physical_map_repository = mock.Mock()
        physical_map_repository.find_spot_id_by_object_id.return_value = SpotId(2)
        continuation_service = PursuitContinuationService(
            world_query_service,
            movement_service=movement_service,
            physical_map_repository=physical_map_repository,
        )

        decision = continuation_service.evaluate_tick(status)

        assert decision.action == PursuitContinuationAction.CONTINUE_PURSUIT
        assert decision.failure_reason is None
        assert status.pursuit_state is not None

    def test_pursuit_continuation_fails_with_target_missing_when_world_lookup_cannot_resolve_target(
        self,
    ):
        status = self._player_status()
        status.start_pursuit(
            PursuitTargetSnapshot(
                target_id=WorldObjectId(70),
                spot_id=SpotId(1),
                coordinate=Coordinate(4, 1, 0),
            )
        )
        status.set_destination(
            Coordinate(1, 0, 0),
            [Coordinate(0, 0, 0), Coordinate(1, 0, 0)],
            goal_spot_id=SpotId(1),
        )
        world_query_service = mock.Mock()
        world_query_service.get_player_current_state.return_value = self._current_state(
            visible_objects=[],
            has_active_path=True,
        )
        physical_map_repository = mock.Mock()
        physical_map_repository.find_spot_id_by_object_id.return_value = None
        continuation_service = PursuitContinuationService(
            world_query_service,
            physical_map_repository=physical_map_repository,
        )

        decision = continuation_service.evaluate_tick(status)

        assert decision.action == PursuitContinuationAction.PURSUIT_FAILED
        assert decision.failure_reason == PursuitFailureReason.TARGET_MISSING
        assert status.has_active_pursuit is False
        assert status.planned_path == []

    def test_pursuit_continuation_fails_with_vision_lost_at_last_known(
        self,
    ):
        status = self._player_status()
        status.start_pursuit(
            PursuitTargetSnapshot(
                target_id=WorldObjectId(71),
                spot_id=SpotId(1),
                coordinate=Coordinate(0, 0, 0),
            )
        )
        world_query_service = mock.Mock()
        world_query_service.get_player_current_state.return_value = self._current_state(
            visible_objects=[],
            has_active_path=False,
        )
        physical_map_repository = mock.Mock()
        physical_map_repository.find_spot_id_by_object_id.return_value = SpotId(1)
        continuation_service = PursuitContinuationService(
            world_query_service,
            physical_map_repository=physical_map_repository,
        )

        decision = continuation_service.evaluate_tick(status)

        assert decision.action == PursuitContinuationAction.PURSUIT_FAILED
        assert decision.failure_reason == (
            PursuitFailureReason.VISION_LOST_AT_LAST_KNOWN
        )
        assert status.has_active_pursuit is False

    def test_pursuit_continuation_fails_with_path_unreachable_for_invisible_target(
        self,
    ):
        status = self._player_status()
        status.start_pursuit(
            PursuitTargetSnapshot(
                target_id=WorldObjectId(72),
                spot_id=SpotId(1),
                coordinate=Coordinate(3, 0, 0),
            )
        )
        movement_service = mock.Mock()
        movement_service.replan_path_to_coordinate_in_current_unit_of_work.return_value = (
            SimpleNamespace(success=False)
        )
        world_query_service = mock.Mock()
        world_query_service.get_player_current_state.return_value = self._current_state(
            visible_objects=[],
            has_active_path=False,
        )
        physical_map_repository = mock.Mock()
        physical_map_repository.find_spot_id_by_object_id.return_value = SpotId(1)
        continuation_service = PursuitContinuationService(
            world_query_service,
            movement_service=movement_service,
            physical_map_repository=physical_map_repository,
        )

        decision = continuation_service.evaluate_tick(status)

        assert decision.action == PursuitContinuationAction.PURSUIT_FAILED
        assert decision.failure_reason == PursuitFailureReason.PATH_UNREACHABLE
        assert status.has_active_pursuit is False
        assert status.planned_path == []

    def test_tick_runs_pursuit_continuation_before_movement_execution(
        self, setup_service
    ):
        service, _, repository, _, player_status_repo, _, _, _, _, _ = setup_service
        status = self._player_status()
        status.start_pursuit(
            PursuitTargetSnapshot(
                target_id=WorldObjectId(77),
                spot_id=SpotId(1),
                coordinate=Coordinate(2, 0, 0),
            )
        )
        status.set_destination(
            Coordinate(1, 0, 0),
            [Coordinate(0, 0, 0), Coordinate(1, 0, 0)],
            goal_destination_type="spot",
            goal_spot_id=SpotId(1),
        )
        player_status_repo.save(status)

        physical_map = PhysicalMapAggregate.create(
            SpotId(1),
            [Tile(Coordinate(x, y, 0), TerrainType.grass()) for x in range(3) for y in range(3)],
            objects=[self._player_actor()],
        )
        repository.save(physical_map)

        order: list[str] = []
        continuation_service = mock.Mock()
        continuation_service.evaluate_tick.side_effect = lambda _: (
            order.append("continuation")
            or PursuitContinuationDecision(
                action=PursuitContinuationAction.CONTINUE_PURSUIT,
                continuation_checked=True,
                should_advance_movement=True,
                replan_required=False,
                replan_attempted=False,
                has_visible_target=True,
                has_active_path=True,
                target_world_object_id=77,
            )
        )
        movement_service = mock.Mock()
        movement_service.tick_movement_in_current_unit_of_work.side_effect = (
            lambda player_id: order.append(f"movement:{player_id}")
        )
        service._pursuit_continuation_service = continuation_service
        service._movement_service = movement_service

        service.tick()

        assert order == ["continuation", "movement:1"]

    def test_tick_runs_monster_lifecycle_before_behavior_stage(self, setup_service):
        service, _, _, _, _, _, _, _, _, _ = setup_service
        order: list[str] = []

        service._monster_lifecycle_stage = mock.Mock()
        service._monster_lifecycle_stage.run.side_effect = (
            lambda maps, active_spot_ids, current_tick: order.append("lifecycle") or set()
        )
        service._monster_behavior_stage = mock.Mock()
        service._monster_behavior_stage.run.side_effect = (
            lambda maps, active_spot_ids, current_tick, skipped_actor_ids=None: order.append("behavior")
        )
        service._hit_box_stage = mock.Mock()
        service._hit_box_stage.run.side_effect = (
            lambda maps, active_spot_ids, current_tick: order.append("hitbox")
        )

        service.tick()

        assert order == ["lifecycle", "behavior", "hitbox"]

    def test_tick_keeps_plain_movement_behavior_when_no_active_pursuit(
        self, setup_service
    ):
        service, _, repository, _, player_status_repo, _, _, _, _, _ = setup_service
        status = self._player_status()
        status.set_destination(
            Coordinate(1, 0, 0),
            [Coordinate(0, 0, 0), Coordinate(1, 0, 0)],
            goal_destination_type="spot",
            goal_spot_id=SpotId(1),
        )
        player_status_repo.save(status)

        physical_map = PhysicalMapAggregate.create(
            SpotId(1),
            [Tile(Coordinate(x, y, 0), TerrainType.grass()) for x in range(3) for y in range(3)],
            objects=[self._player_actor()],
        )
        repository.save(physical_map)

        continuation_service = mock.Mock()
        movement_service = mock.Mock()
        service._pursuit_continuation_service = continuation_service
        service._movement_service = movement_service

        service.tick()

        continuation_service.evaluate_tick.assert_not_called()
        movement_service.tick_movement_in_current_unit_of_work.assert_called_once_with(1)

    def test_tick_skips_busy_pursuit_actor_without_continuation_or_movement(
        self, setup_service
    ):
        service, _, repository, _, player_status_repo, _, _, _, _, _ = setup_service
        status = self._player_status()
        status.start_pursuit(
            PursuitTargetSnapshot(
                target_id=WorldObjectId(88),
                spot_id=SpotId(1),
                coordinate=Coordinate(2, 0, 0),
            )
        )
        status.set_destination(
            Coordinate(1, 0, 0),
            [Coordinate(0, 0, 0), Coordinate(1, 0, 0)],
            goal_destination_type="spot",
            goal_spot_id=SpotId(1),
        )
        player_status_repo.save(status)

        physical_map = PhysicalMapAggregate.create(
            SpotId(1),
            [Tile(Coordinate(x, y, 0), TerrainType.grass()) for x in range(3) for y in range(3)],
            objects=[self._player_actor(busy_until=WorldTick(99))],
        )
        repository.save(physical_map)

        continuation_service = mock.Mock()
        movement_service = mock.Mock()
        service._pursuit_continuation_service = continuation_service
        service._movement_service = movement_service

        service.tick()

        updated_status = player_status_repo.find_by_id(PlayerId(1))
        assert updated_status is not None
        assert updated_status.has_active_pursuit is True
        continuation_service.evaluate_tick.assert_not_called()
        movement_service.tick_movement_in_current_unit_of_work.assert_not_called()

    def test_tick_processes_pathless_pursuit_before_skipping_movement(
        self, setup_service
    ):
        service, _, repository, _, player_status_repo, _, _, _, _, _ = setup_service
        status = self._player_status()
        status.start_pursuit(
            PursuitTargetSnapshot(
                target_id=WorldObjectId(55),
                spot_id=SpotId(1),
                coordinate=Coordinate(2, 0, 0),
            )
        )
        player_status_repo.save(status)

        physical_map = PhysicalMapAggregate.create(
            SpotId(1),
            [Tile(Coordinate(x, y, 0), TerrainType.grass()) for x in range(3) for y in range(3)],
            objects=[self._player_actor()],
        )
        repository.save(physical_map)

        continuation_service = mock.Mock(
            return_value=PursuitContinuationDecision(
                action=PursuitContinuationAction.CONTINUE_PURSUIT,
                continuation_checked=True,
                should_advance_movement=True,
                replan_required=True,
                replan_attempted=True,
                has_visible_target=False,
                has_active_path=True,
                target_world_object_id=55,
            )
        )
        continuation_service.evaluate_tick.return_value = PursuitContinuationDecision(
            action=PursuitContinuationAction.CONTINUE_PURSUIT,
            continuation_checked=True,
            should_advance_movement=True,
            replan_required=True,
            replan_attempted=True,
            has_visible_target=False,
            has_active_path=True,
            target_world_object_id=55,
        )
        movement_service = mock.Mock()
        service._pursuit_continuation_service = continuation_service
        service._movement_service = movement_service

        service.tick()

        continuation_service.evaluate_tick.assert_called_once()
        movement_service.tick_movement_in_current_unit_of_work.assert_called_once_with(1)

    def test_tick_visible_pursuit_refreshes_target_and_moves_in_same_tick(
        self, setup_service
    ):
        service, _, repository, _, player_status_repo, _, _, _, _, _ = setup_service
        status = self._player_status()
        status.start_pursuit(
            PursuitTargetSnapshot(
                target_id=WorldObjectId(91),
                spot_id=SpotId(1),
                coordinate=Coordinate(1, 0, 0),
            )
        )
        player_status_repo.save(status)

        physical_map = PhysicalMapAggregate.create(
            SpotId(1),
            [Tile(Coordinate(x, y, 0), TerrainType.grass()) for x in range(4) for y in range(2)],
            objects=[
                self._player_actor(),
                WorldObject(
                    WorldObjectId(91),
                    Coordinate(2, 0, 0),
                    ObjectTypeEnum.NPC,
                    is_blocking=False,
                ),
            ],
        )
        repository.save(physical_map)

        world_query_service = mock.Mock()
        world_query_service.get_player_current_state.return_value = self._current_state(
            visible_objects=[self._visible_target(91, x=2, y=0)],
            has_active_path=False,
        )
        movement_service = mock.Mock()
        movement_service.replan_path_to_coordinate_in_current_unit_of_work.return_value = (
            SimpleNamespace(success=True)
        )

        def advance_one_step(player_id: int) -> None:
            updated_status = player_status_repo.find_by_id(PlayerId(player_id))
            assert updated_status is not None
            updated_status.update_location(SpotId(1), Coordinate(1, 0, 0))
            player_status_repo.save(updated_status)
            latest_map = repository.find_by_spot_id(SpotId(1))
            assert latest_map is not None
            latest_map.get_actor(WorldObjectId(player_id)).move_to(Coordinate(1, 0, 0))
            repository.save(latest_map)

        movement_service.tick_movement_in_current_unit_of_work.side_effect = advance_one_step
        service._movement_service = movement_service
        service._pursuit_continuation_service = PursuitContinuationService(
            world_query_service,
            movement_service=movement_service,
            physical_map_repository=repository,
        )

        service.tick()

        saved_status = player_status_repo.find_by_id(PlayerId(1))
        updated_map = repository.find_by_spot_id(SpotId(1))
        assert saved_status is not None
        assert saved_status.pursuit_state is not None
        assert saved_status.current_coordinate == Coordinate(1, 0, 0)
        assert saved_status.pursuit_state.target_snapshot.coordinate == Coordinate(2, 0, 0)
        assert saved_status.pursuit_state.last_known.coordinate == Coordinate(2, 0, 0)
        assert updated_map is not None
        assert updated_map.get_actor(WorldObjectId(1)).coordinate == Coordinate(1, 0, 0)

    def test_tick_lost_visibility_moves_to_frozen_last_known_then_fails_after_arrival(
        self, setup_service
    ):
        service, _, repository, _, player_status_repo, _, _, _, _, _ = setup_service
        status = self._player_status()
        status.start_pursuit(
            PursuitTargetSnapshot(
                target_id=WorldObjectId(92),
                spot_id=SpotId(1),
                coordinate=Coordinate(1, 0, 0),
            )
        )
        player_status_repo.save(status)

        pursuit_events: list[object] = []

        player_map = PhysicalMapAggregate.create(
            SpotId(1),
            [Tile(Coordinate(x, y, 0), TerrainType.grass()) for x in range(3) for y in range(2)],
            objects=[self._player_actor()],
        )
        target_map = PhysicalMapAggregate.create(
            SpotId(2),
            [Tile(Coordinate(x, y, 0), TerrainType.grass()) for x in range(3) for y in range(2)],
            objects=[
                WorldObject(
                    WorldObjectId(92),
                    Coordinate(2, 0, 0),
                    ObjectTypeEnum.NPC,
                    is_blocking=False,
                )
            ],
        )
        repository.save(player_map)
        repository.save(target_map)

        world_query_service = mock.Mock()
        world_query_service.get_player_current_state.return_value = self._current_state(
            visible_objects=[],
            has_active_path=False,
        )
        movement_service = mock.Mock()
        movement_service.replan_path_to_coordinate_in_current_unit_of_work.return_value = (
            SimpleNamespace(success=True)
        )

        def advance_one_step(player_id: int) -> None:
            updated_status = player_status_repo.find_by_id(PlayerId(player_id))
            assert updated_status is not None
            updated_status.update_location(SpotId(1), Coordinate(1, 0, 0))
            player_status_repo.save(updated_status)
            latest_map = repository.find_by_spot_id(SpotId(1))
            assert latest_map is not None
            latest_map.get_actor(WorldObjectId(player_id)).move_to(Coordinate(1, 0, 0))
            repository.save(latest_map)

        movement_service.tick_movement_in_current_unit_of_work.side_effect = advance_one_step
        service._movement_service = movement_service
        service._pursuit_continuation_service = PursuitContinuationService(
            world_query_service,
            movement_service=movement_service,
            physical_map_repository=repository,
        )

        service.tick()

        saved_after_first_tick = player_status_repo.find_by_id(PlayerId(1))
        assert saved_after_first_tick is not None
        assert saved_after_first_tick.has_active_pursuit is True
        assert saved_after_first_tick.current_coordinate == Coordinate(1, 0, 0)
        assert saved_after_first_tick.pursuit_state is not None
        assert saved_after_first_tick.pursuit_state.last_known.coordinate == Coordinate(1, 0, 0)
        pursuit_events.extend(saved_after_first_tick.get_events())
        saved_after_first_tick.clear_events()
        assert not any(
            getattr(event, "failure_reason", None) is not None for event in pursuit_events
        )

        service.tick()

        saved_after_second_tick = player_status_repo.find_by_id(PlayerId(1))
        assert saved_after_second_tick is not None
        assert saved_after_second_tick.has_active_pursuit is False
        assert saved_after_second_tick.current_coordinate == Coordinate(1, 0, 0)
        pursuit_events.extend(saved_after_second_tick.get_events())
        movement_service.tick_movement_in_current_unit_of_work.assert_called_once_with(1)
        assert any(
            getattr(event, "failure_reason", None)
            == PursuitFailureReason.VISION_LOST_AT_LAST_KNOWN
            for event in pursuit_events
        )

    def test_tick_stops_movement_when_pursuit_fails_with_structured_reason(
        self, setup_service
    ):
        service, _, repository, _, player_status_repo, _, _, _, _, _ = setup_service
        status = self._player_status()
        status.start_pursuit(
            PursuitTargetSnapshot(
                target_id=WorldObjectId(55),
                spot_id=SpotId(1),
                coordinate=Coordinate(2, 0, 0),
            )
        )
        player_status_repo.save(status)

        physical_map = PhysicalMapAggregate.create(
            SpotId(1),
            [Tile(Coordinate(x, y, 0), TerrainType.grass()) for x in range(3) for y in range(3)],
            objects=[self._player_actor()],
        )
        repository.save(physical_map)

        service._pursuit_continuation_service = mock.Mock()
        service._pursuit_continuation_service.evaluate_tick.return_value = (
            PursuitContinuationDecision(
                action=PursuitContinuationAction.PURSUIT_FAILED,
                continuation_checked=True,
                should_advance_movement=False,
                replan_required=False,
                replan_attempted=False,
                has_visible_target=False,
                has_active_path=False,
                target_world_object_id=55,
                failure_reason=PursuitFailureReason.TARGET_MISSING,
            )
        )
        service._movement_service = mock.Mock()

        service.tick()

        service._movement_service.tick_movement_in_current_unit_of_work.assert_not_called()

    def test_tick_updates_autonomous_actors(self, setup_service):
        """tickによって自律行動アクター（モンスター）の行動が計画・実行されること（アクティブスポットのみ更新）"""
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
                vision_range=5,
                patrol_points=[Coordinate(2, 2), Coordinate(2, 3)],
            ),
        )
        physical_map.add_object(actor)
        repository.save(physical_map)

        template = MonsterTemplate(
            template_id=MonsterTemplateId(1),
            name="Slime",
            base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
            reward_info=RewardInfo(0, 0),
            respawn_info=RespawnInfo(1, True),
            race=Race.HUMAN,
            faction=MonsterFactionEnum.ENEMY,
            description="Slime",
            skill_ids=[],
        )
        loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), actor_id.value, 10, 10)
        monster = MonsterAggregate.create(MonsterId(1), template, actor_id, skill_loadout=loadout)
        monster.spawn(Coordinate(2, 2, 0), spot_id, WorldTick(0))
        monster_repo.save(monster)
        skill_loadout_repo.save(loadout)

        # リゾルバが MOVE(2,3) を返すようにモック（decide → 移動イベント → ハンドラで座標更新）
        move_action = BehaviorAction.move(Coordinate(2, 3))
        fake_resolver = mock.Mock()
        fake_resolver.resolve_action.return_value = move_action
        with mock.patch.object(service, "_monster_action_resolver_factory", return_value=fake_resolver):
            service.tick()

        updated_map = repository.find_by_spot_id(spot_id)
        updated_actor = updated_map.get_object(actor_id)
        assert updated_actor.coordinate == Coordinate(2, 3)

    def test_tick_publishes_behavior_events_from_monster_aggregate(self, setup_service):
        """tick で自律アクターがモンスターの場合、行動イベントがモンスター集約経由で発行されること（Map に積まれない）"""
        service, _, repository, _, _, _, _, event_publisher, monster_repo, skill_loadout_repo = setup_service
        from ai_rpg_world.domain.world.service.hostility_service import ConfigurableHostilityService

        # 敵対設定: goblin が human を敵視するようにする
        service._behavior_service._hostility_service = ConfigurableHostilityService(
            race_disposition_table={"goblin": {"human": Disposition.HOSTILE}}
        )

        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        player_id = PlayerId(100)
        physical_map.add_object(WorldObject(
            WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
            component=ActorComponent(player_id=player_id, race="human"),
        ))
        actor_id = WorldObjectId(1)
        physical_map.add_object(WorldObject(
            actor_id,
            Coordinate(1, 0),
            ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(race="goblin", vision_range=5, fov_angle=360),
        ))
        repository.save(physical_map)

        # 同一 actor_id でモンスター集約を登録（tick で find_by_world_object_id が返す）
        template = MonsterTemplate(
            template_id=MonsterTemplateId(1),
            name="Goblin",
            base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
            reward_info=RewardInfo(0, 0),
            respawn_info=RespawnInfo(1, True),
            race=Race.HUMAN,
            faction=MonsterFactionEnum.ENEMY,
            description="Goblin",
            skill_ids=[],
        )
        loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), actor_id.value, 10, 10)
        monster = MonsterAggregate.create(MonsterId(1), template, actor_id, skill_loadout=loadout)
        monster.spawn(Coordinate(1, 0, 0), spot_id, WorldTick(0))
        monster_repo.save(monster)
        skill_loadout_repo.save(loadout)

        service.tick()

        # 行動イベントが発行されていること（モンスターに積んで save → commit で発行）
        events = event_publisher.get_published_events()
        assert any(isinstance(e, (TargetSpottedEvent, ActorStateChangedEvent)) for e in events), (
            f"Expected TargetSpottedEvent or ActorStateChangedEvent in published events, got: {[type(e).__name__ for e in events]}"
        )

    def test_tick_visible_monster_target_starts_aligned_pursuit_state(self, setup_service):
        """通常の tick で可視ターゲットを見つけたモンスターが aligned pursuit state を保持すること"""
        service, _, repository, _, _, _, _, _, monster_repo, skill_loadout_repo = setup_service
        from ai_rpg_world.domain.world.service.hostility_service import ConfigurableHostilityService

        service._behavior_service._hostility_service = ConfigurableHostilityService(
            race_disposition_table={"goblin": {"human": Disposition.HOSTILE}}
        )

        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        player_id = PlayerId(100)
        physical_map.add_object(
            WorldObject(
                WorldObjectId(100),
                Coordinate(0, 0, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=player_id, race="human"),
            )
        )
        actor_id = WorldObjectId(1)
        physical_map.add_object(
            WorldObject(
                actor_id,
                Coordinate(1, 0, 0),
                ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(race="goblin", vision_range=5, fov_angle=360),
            )
        )
        repository.save(physical_map)

        template = MonsterTemplate(
            template_id=MonsterTemplateId(1),
            name="Goblin",
            base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
            reward_info=RewardInfo(0, 0),
            respawn_info=RespawnInfo(1, True),
            race=Race.HUMAN,
            faction=MonsterFactionEnum.ENEMY,
            description="Goblin",
            skill_ids=[],
        )
        loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), actor_id.value, 10, 10)
        monster = MonsterAggregate.create(MonsterId(1), template, actor_id, skill_loadout=loadout)
        monster.spawn(Coordinate(1, 0, 0), spot_id, WorldTick(0))
        monster_repo.save(monster)
        skill_loadout_repo.save(loadout)

        service.tick()

        saved_monster = monster_repo.find_by_world_object_id(actor_id)
        assert saved_monster is not None
        assert saved_monster.behavior_state == BehaviorStateEnum.CHASE
        assert saved_monster.has_active_pursuit is True
        assert saved_monster.pursuit_state is not None
        assert saved_monster.pursuit_state.target_id == WorldObjectId(100)
        assert saved_monster.pursuit_state.target_snapshot is not None
        assert saved_monster.pursuit_state.target_snapshot.coordinate == Coordinate(0, 0, 0)
        assert saved_monster.pursuit_state.last_known is not None
        assert saved_monster.pursuit_state.last_known.coordinate == Coordinate(0, 0, 0)

    def test_tick_monster_search_at_last_known_fails_with_shared_reason(
        self, setup_service
    ):
        service, _, repository, _, _, _, _, event_publisher, monster_repo, skill_loadout_repo = setup_service

        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(4) for y in range(4)]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        physical_map.add_object(
            WorldObject(
                WorldObjectId(200),
                Coordinate(3, 3, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(200), race="human"),
            )
        )
        actor_id = WorldObjectId(1)
        actor_coordinate = Coordinate(1, 0, 0)
        physical_map.add_object(
            WorldObject(
                actor_id,
                actor_coordinate,
                ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(race="goblin", vision_range=5, fov_angle=360),
            )
        )
        repository.save(physical_map)

        template = MonsterTemplate(
            template_id=MonsterTemplateId(1),
            name="Goblin",
            base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
            reward_info=RewardInfo(0, 0),
            respawn_info=RespawnInfo(1, True),
            race=Race.HUMAN,
            faction=MonsterFactionEnum.ENEMY,
            description="Goblin",
            skill_ids=[],
        )
        loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), actor_id.value, 10, 10)
        monster = MonsterAggregate.create(MonsterId(1), template, actor_id, skill_loadout=loadout)
        monster.spawn(actor_coordinate, spot_id, WorldTick(0))
        target_id = WorldObjectId(100)
        monster._behavior_state = BehaviorStateEnum.SEARCH
        monster._behavior_target_id = target_id
        monster._behavior_last_known_position = actor_coordinate
        monster._pursuit_state = PursuitState(
            actor_id=actor_id,
            target_id=target_id,
            target_snapshot=PursuitTargetSnapshot(
                target_id=target_id,
                spot_id=spot_id,
                coordinate=Coordinate(2, 0, 0),
            ),
            last_known=PursuitLastKnownState(
                target_id=target_id,
                spot_id=spot_id,
                coordinate=actor_coordinate,
                observed_at_tick=WorldTick(1),
            ),
        )
        monster_repo.save(monster)
        skill_loadout_repo.save(loadout)

        service.tick()

        saved_monster = monster_repo.find_by_world_object_id(actor_id)
        assert saved_monster is not None
        assert saved_monster.has_active_pursuit is False
        assert saved_monster.behavior_target_id is None
        assert saved_monster.behavior_last_known_position is None

        pursuit_failed_events = [
            event
            for event in event_publisher.get_published_events()
            if isinstance(event, PursuitFailedEvent)
        ]
        assert any(
            event.actor_id == actor_id
            and event.failure_reason == PursuitFailureReason.VISION_LOST_AT_LAST_KNOWN
            for event in pursuit_failed_events
        )

    def test_tick_monster_search_reacquires_same_target_and_resumes_chase(
        self, setup_service
    ):
        service, _, repository, _, _, _, _, _, monster_repo, skill_loadout_repo = setup_service
        service._behavior_service._hostility_service = ConfigurableHostilityService(
            race_disposition_table={"goblin": {"human": Disposition.HOSTILE}}
        )

        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(6) for y in range(4)]
        target_id = WorldObjectId(100)
        player_id = PlayerId(100)
        physical_map = PhysicalMapAggregate.create(
            spot_id,
            tiles,
            objects=[
                WorldObject(
                    target_id,
                    Coordinate(3, 0, 0),
                    ObjectTypeEnum.PLAYER,
                    component=ActorComponent(player_id=player_id, race="human"),
                ),
                WorldObject(
                    WorldObjectId(1),
                    Coordinate(1, 0, 0),
                    ObjectTypeEnum.NPC,
                    component=AutonomousBehaviorComponent(race="goblin", vision_range=5, fov_angle=360),
                ),
            ],
        )
        repository.save(physical_map)

        template = MonsterTemplate(
            template_id=MonsterTemplateId(1),
            name="Goblin",
            base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
            reward_info=RewardInfo(0, 0),
            respawn_info=RespawnInfo(1, True),
            race=Race.HUMAN,
            faction=MonsterFactionEnum.ENEMY,
            description="Goblin",
            skill_ids=[],
        )
        loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), 1, 10, 10)
        monster = MonsterAggregate.create(MonsterId(1), template, WorldObjectId(1), skill_loadout=loadout)
        monster.spawn(Coordinate(1, 0, 0), spot_id, WorldTick(0))
        monster._behavior_state = BehaviorStateEnum.SEARCH
        monster._behavior_target_id = target_id
        monster._behavior_last_known_position = Coordinate(2, 0, 0)
        monster._pursuit_state = PursuitState(
            actor_id=WorldObjectId(1),
            target_id=target_id,
            target_snapshot=PursuitTargetSnapshot(
                target_id=target_id,
                spot_id=spot_id,
                coordinate=Coordinate(2, 0, 0),
            ),
            last_known=PursuitLastKnownState(
                target_id=target_id,
                spot_id=spot_id,
                coordinate=Coordinate(2, 0, 0),
                observed_at_tick=WorldTick(1),
            ),
        )
        monster_repo.save(monster)
        skill_loadout_repo.save(loadout)

        service.tick()

        saved_monster = monster_repo.find_by_world_object_id(WorldObjectId(1))
        assert saved_monster is not None
        assert saved_monster.behavior_state == BehaviorStateEnum.CHASE
        assert saved_monster.behavior_target_id == target_id
        assert saved_monster.pursuit_state is not None
        assert saved_monster.pursuit_state.target_id == target_id
        assert saved_monster.pursuit_state.target_snapshot is not None
        assert saved_monster.pursuit_state.target_snapshot.coordinate == Coordinate(3, 0, 0)
        assert saved_monster.pursuit_state.last_known is not None
        assert saved_monster.pursuit_state.last_known.coordinate == Coordinate(3, 0, 0)

    def test_tick_monster_missing_target_fails_with_target_missing_and_clears_state(
        self, setup_service
    ):
        service, _, repository, _, _, _, _, event_publisher, monster_repo, skill_loadout_repo = setup_service

        spot_id = SpotId(1)
        tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(4)]
        physical_map = PhysicalMapAggregate.create(spot_id, tiles)
        physical_map.add_object(
            WorldObject(
                WorldObjectId(200),
                Coordinate(4, 3, 0),
                ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(200), race="human"),
            )
        )
        actor_id = WorldObjectId(1)
        actor_coordinate = Coordinate(0, 0, 0)
        physical_map.add_object(
            WorldObject(
                actor_id,
                actor_coordinate,
                ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(race="goblin", vision_range=5, fov_angle=360),
            )
        )
        repository.save(physical_map)

        template = MonsterTemplate(
            template_id=MonsterTemplateId(1),
            name="Goblin",
            base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
            reward_info=RewardInfo(0, 0),
            respawn_info=RespawnInfo(1, True),
            race=Race.HUMAN,
            faction=MonsterFactionEnum.ENEMY,
            description="Goblin",
            skill_ids=[],
        )
        loadout = SkillLoadoutAggregate.create(SkillLoadoutId(1), actor_id.value, 10, 10)
        monster = MonsterAggregate.create(MonsterId(1), template, actor_id, skill_loadout=loadout)
        monster.spawn(actor_coordinate, spot_id, WorldTick(0))
        target_id = WorldObjectId(999)
        monster._behavior_state = BehaviorStateEnum.SEARCH
        monster._behavior_target_id = target_id
        monster._behavior_last_known_position = Coordinate(2, 0, 0)
        monster._pursuit_state = PursuitState(
            actor_id=actor_id,
            target_id=target_id,
            target_snapshot=PursuitTargetSnapshot(
                target_id=target_id,
                spot_id=spot_id,
                coordinate=Coordinate(2, 0, 0),
            ),
            last_known=PursuitLastKnownState(
                target_id=target_id,
                spot_id=spot_id,
                coordinate=Coordinate(2, 0, 0),
                observed_at_tick=WorldTick(1),
            ),
        )
        monster_repo.save(monster)
        skill_loadout_repo.save(loadout)

        service.tick()

        saved_monster = monster_repo.find_by_world_object_id(actor_id)
        assert saved_monster is not None
        assert saved_monster.has_active_pursuit is False
        assert saved_monster.behavior_target_id is None
        assert saved_monster.behavior_last_known_position is None

        pursuit_failed_events = [
            event
            for event in event_publisher.get_published_events()
            if isinstance(event, PursuitFailedEvent)
        ]
        assert any(
            event.actor_id == actor_id
            and event.failure_reason == PursuitFailureReason.TARGET_MISSING
            for event in pursuit_failed_events
        )

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
        """1つのモンスターでエラーが発生しても他のモンスターの更新が継続されること"""
        service, _, repository, _, _, _, _, _, monster_repo, skill_loadout_repo = setup_service

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
            component=AutonomousBehaviorComponent(patrol_points=[Coordinate(2, 2), Coordinate(2, 3)]),
        )
        actor2 = WorldObject(
            actor2_id, Coordinate(3, 3), ObjectTypeEnum.NPC,
            component=AutonomousBehaviorComponent(patrol_points=[Coordinate(3, 3), Coordinate(3, 4)]),
        )
        physical_map.add_object(actor1)
        physical_map.add_object(actor2)
        repository.save(physical_map)

        def _add_monster(wo_id, mid, coord):
            loadout = SkillLoadoutAggregate.create(SkillLoadoutId(mid), wo_id.value, 10, 10)
            t = MonsterTemplate(
                template_id=MonsterTemplateId(mid),
                name="M",
                base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
                reward_info=RewardInfo(0, 0),
                respawn_info=RespawnInfo(1, True),
                race=Race.HUMAN,
                faction=MonsterFactionEnum.ENEMY,
                description="M",
                skill_ids=[],
            )
            m = MonsterAggregate.create(MonsterId(mid), t, wo_id, skill_loadout=loadout)
            m.spawn(coord, spot_id, WorldTick(0))
            monster_repo.save(m)
            skill_loadout_repo.save(loadout)

        _add_monster(actor1_id, 1, Coordinate(2, 2, 0))
        _add_monster(actor2_id, 2, Coordinate(3, 3, 0))

        def build_observation_side_effect(actor_id_arg, map_agg, **kwargs):
            from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
            if actor_id_arg == actor1_id:
                raise Exception("Plan error")
            return BehaviorObservation()

        # actor2 はリゾルバが MOVE(3,4) を返すようにモック
        move_action = BehaviorAction.move(Coordinate(3, 4))
        fake_resolver = mock.Mock()
        fake_resolver.resolve_action.return_value = move_action
        with mock.patch.object(service._behavior_service, "build_observation", side_effect=build_observation_side_effect):
            with mock.patch.object(service, "_monster_action_resolver_factory", return_value=fake_resolver):
                service.tick()

        updated_map = repository.find_by_spot_id(spot_id)
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
            vision_range=5,
            available_skills=skills,
            fov_angle=360.0,
        )
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
            reward_info=RewardInfo(10, 10, 1),
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
        
        # リゾルバが USE_SKILL を返すようにモック（decide が MonsterDecidedToUseSkillEvent を発行しハンドラが実行）
        use_skill_action = BehaviorAction(
            action_type=BehaviorActionType.USE_SKILL,
            coordinate=None,
            skill_slot_index=0,
        )
        fake_resolver = mock.Mock()
        fake_resolver.resolve_action.return_value = use_skill_action
        with mock.patch.object(service, "_monster_action_resolver_factory", return_value=fake_resolver):
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
        """skill_context / target_context の組み立てと build_observation への渡し（正常・境界）"""

        def test_build_observation_receives_skill_context_for_monster_with_usable_slots(self, setup_service):
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
            def capture_build_observation(actor_id_arg, map_agg, **kwargs):
                from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
                captured.append(kwargs)
                return BehaviorObservation(**{k: kwargs.get(k) for k in (
                    "visible_threats", "visible_hostiles", "selected_target", "skill_context",
                    "growth_context", "target_context", "pack_rally_coordinate", "current_tick",
                ) if k in kwargs})

            with mock.patch.object(service._behavior_service, "build_observation", side_effect=capture_build_observation):
                service.tick()

            assert len(captured) == 1
            ctx = captured[0]["skill_context"]
            assert isinstance(ctx, SkillSelectionContext)
            assert 0 in ctx.usable_slot_indices

        def test_build_observation_receives_none_skill_context_for_non_autonomous_actor(self, setup_service):
            # プレイヤーのみのマップでは自律アクターがおらず build_observation は呼ばれない（モンスターのみ処理するため）
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)
            physical_map.add_object(WorldObject(
                WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(100)),
            ))
            repository.save(physical_map)

            captured = []
            def capture_build_observation(actor_id_arg, map_agg, **kwargs):
                from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
                captured.append(kwargs)
                return BehaviorObservation()

            with mock.patch.object(service._behavior_service, "build_observation", side_effect=capture_build_observation):
                service.tick()

            assert len(captured) == 0

        def test_build_observation_receives_target_context_when_aggro_store_has_data(self, setup_service):
            # Given: aggro_store を注入し、該当アクターのヘイトデータを事前に登録（アクティブスポットのためプレイヤーを配置）
            service, _, repository, _, _, _, _, _, monster_repo, skill_loadout_repo = setup_service
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

            loadout = SkillLoadoutAggregate.create(SkillLoadoutId.create(1), 1, 10, 10)
            skill_loadout_repo.save(loadout)
            monster = MonsterAggregate.create(
                MonsterId(1),
                MonsterTemplate(
                    template_id=MonsterTemplateId(1),
                    name="M",
                    base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
                    reward_info=RewardInfo(0, 0),
                    respawn_info=RespawnInfo(1, True),
                    race=Race.HUMAN,
                    faction=MonsterFactionEnum.ENEMY,
                    description="M",
                    skill_ids=[],
                ),
                WorldObjectId(1),
                skill_loadout=loadout,
            )
            monster.spawn(Coordinate(2, 2, 0), spot_id, WorldTick(0))
            monster_repo.save(monster)

            captured = []
            def capture_build_observation(actor_id_arg, map_agg, **kwargs):
                from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
                captured.append(kwargs)
                return BehaviorObservation(**{k: kwargs.get(k) for k in (
                    "visible_threats", "visible_hostiles", "selected_target", "skill_context",
                    "growth_context", "target_context", "pack_rally_coordinate", "current_tick",
                ) if k in kwargs})

            with mock.patch.object(service._behavior_service, "build_observation", side_effect=capture_build_observation):
                service.tick()

            assert len(captured) == 1
            ctx = captured[0]["target_context"]
            assert isinstance(ctx, TargetSelectionContext)
            assert ctx.threat_by_id == {WorldObjectId(200): 5}

        def test_build_observation_receives_none_target_context_when_aggro_store_not_injected(self, setup_service):
            # aggro_store は None（デフォルト）。モンスター1体で build_observation が1回呼ばれ target_context は None
            service, _, repository, _, _, _, _, _, monster_repo, skill_loadout_repo = setup_service
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

            loadout = SkillLoadoutAggregate.create(SkillLoadoutId.create(1), 1, 10, 10)
            skill_loadout_repo.save(loadout)
            monster = MonsterAggregate.create(
                MonsterId(1),
                MonsterTemplate(
                    template_id=MonsterTemplateId(1),
                    name="M",
                    base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
                    reward_info=RewardInfo(0, 0),
                    respawn_info=RespawnInfo(1, True),
                    race=Race.HUMAN,
                    faction=MonsterFactionEnum.ENEMY,
                    description="M",
                    skill_ids=[],
                ),
                WorldObjectId(1),
                skill_loadout=loadout,
            )
            monster.spawn(Coordinate(2, 2, 0), spot_id, WorldTick(0))
            monster_repo.save(monster)

            captured = []
            def capture_build_observation(actor_id_arg, map_agg, **kwargs):
                from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
                captured.append(kwargs)
                return BehaviorObservation(**{k: kwargs.get(k) for k in (
                    "visible_threats", "visible_hostiles", "selected_target", "skill_context",
                    "growth_context", "target_context", "pack_rally_coordinate", "current_tick",
                ) if k in kwargs})

            with mock.patch.object(service._behavior_service, "build_observation", side_effect=capture_build_observation):
                service.tick()

            assert len(captured) == 1
            assert captured[0].get("target_context") is None

        def test_build_observation_receives_target_context_with_memory_policy_forgotten_excluded(self, setup_service):
            """aggro_memory_policy で忘却済みのヘイトは target_context に含まれないこと（last_seen から経過で忘却）"""
            service, _, repository, _, _, _, _, _, monster_repo, skill_loadout_repo = setup_service
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

            loadout = SkillLoadoutAggregate.create(SkillLoadoutId.create(1), 1, 10, 10)
            skill_loadout_repo.save(loadout)
            monster = MonsterAggregate.create(
                MonsterId(1),
                MonsterTemplate(
                    template_id=MonsterTemplateId(1),
                    name="M",
                    base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
                    reward_info=RewardInfo(0, 0),
                    respawn_info=RespawnInfo(1, True),
                    race=Race.HUMAN,
                    faction=MonsterFactionEnum.ENEMY,
                    description="M",
                    skill_ids=[],
                ),
                WorldObjectId(1),
                skill_loadout=loadout,
            )
            monster.spawn(Coordinate(2, 2, 0), spot_id, WorldTick(0))
            monster_repo.save(monster)

            captured = []
            def capture_build_observation(actor_id_arg, map_agg, **kwargs):
                from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
                captured.append(kwargs)
                return BehaviorObservation(**{k: kwargs.get(k) for k in (
                    "visible_threats", "visible_hostiles", "selected_target", "skill_context",
                    "growth_context", "target_context", "pack_rally_coordinate", "current_tick",
                ) if k in kwargs})

            with mock.patch.object(service._behavior_service, "build_observation", side_effect=capture_build_observation):
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
            """同一マップにプレイヤーがいる場合、モンスターはプレイヤーに近い順に build_observation が呼ばれること"""
            service, _, repository, _, _, _, _, _, monster_repo, skill_loadout_repo = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(10) for y in range(10)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)

            physical_map.add_object(WorldObject(
                WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(100)),
            ))

            near_id = WorldObjectId(1)
            mid_id = WorldObjectId(2)
            far_id = WorldObjectId(3)
            template = MonsterTemplate(
                template_id=MonsterTemplateId(1),
                name="M",
                base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
                reward_info=RewardInfo(0, 0),
                respawn_info=RespawnInfo(1, True),
                race=Race.HUMAN,
                faction=MonsterFactionEnum.ENEMY,
                description="M",
                skill_ids=[],
            )
            for oid, coord in [(near_id, Coordinate(1, 0)), (mid_id, Coordinate(3, 0)), (far_id, Coordinate(5, 0))]:
                physical_map.add_object(WorldObject(
                    oid, coord, ObjectTypeEnum.NPC,
                    component=AutonomousBehaviorComponent(patrol_points=[coord, coord]),
                ))
                loadout = SkillLoadoutAggregate.create(SkillLoadoutId.create(oid.value), 1, 10, 10)
                skill_loadout_repo.save(loadout)
                monster = MonsterAggregate.create(MonsterId(oid.value), template, oid, skill_loadout=loadout)
                monster.spawn(Coordinate(coord.x, coord.y, 0), spot_id, WorldTick(0))
                monster_repo.save(monster)
            repository.save(physical_map)

            call_order = []
            def capture_order(actor_id_arg, map_agg, **kwargs):
                from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
                call_order.append(actor_id_arg)
                return BehaviorObservation(**{k: kwargs.get(k) for k in (
                    "visible_threats", "visible_hostiles", "selected_target", "skill_context",
                    "growth_context", "target_context", "pack_rally_coordinate", "current_tick",
                ) if k in kwargs})

            with mock.patch.object(service._behavior_service, "build_observation", side_effect=capture_order):
                service.tick()

            assert len(call_order) == 3
            assert call_order[0] == near_id
            assert call_order[1] == mid_id
            assert call_order[2] == far_id

        def test_actors_processed_when_no_player_on_map(self, setup_service):
            """同一マップにプレイヤーがいない場合、そのスポットは凍結され build_observation は呼ばれないこと"""
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)

            for i, coord in enumerate([Coordinate(1, 1), Coordinate(2, 2), Coordinate(3, 3)]):
                actor_id = WorldObjectId(10 + i)
                physical_map.add_object(WorldObject(
                    actor_id, coord, ObjectTypeEnum.NPC,
                    component=AutonomousBehaviorComponent(patrol_points=[coord, coord]),
                ))
            repository.save(physical_map)

            call_count = [0]
            def count_calls(actor_id_arg, map_agg, **kwargs):
                call_count[0] += 1
                return BehaviorAction.move(Coordinate(0, 0))

            with mock.patch.object(service._behavior_service, "build_observation", side_effect=count_calls):
                service.tick()

            assert call_count[0] == 0

        def test_actors_sorted_by_nearest_player_when_multiple_players(self, setup_service):
            """同一マップに複数プレイヤーがいる場合、モンスターは最も近いプレイヤーとの距離でソートされ build_observation が呼ばれること"""
            service, _, repository, _, _, _, _, _, monster_repo, skill_loadout_repo = setup_service
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
            template = MonsterTemplate(
                template_id=MonsterTemplateId(1),
                name="M",
                base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
                reward_info=RewardInfo(0, 0),
                respawn_info=RespawnInfo(1, True),
                race=Race.HUMAN,
                faction=MonsterFactionEnum.ENEMY,
                description="M",
                skill_ids=[],
            )
            for oid, coord in [
                (near_p1_id, Coordinate(1, 0)),
                (mid_id, Coordinate(5, 0)),
                (near_p2_id, Coordinate(9, 0)),
            ]:
                physical_map.add_object(WorldObject(
                    oid, coord, ObjectTypeEnum.NPC,
                    component=AutonomousBehaviorComponent(patrol_points=[coord, coord]),
                ))
                loadout = SkillLoadoutAggregate.create(SkillLoadoutId.create(oid.value), 1, 10, 10)
                skill_loadout_repo.save(loadout)
                monster = MonsterAggregate.create(MonsterId(oid.value), template, oid, skill_loadout=loadout)
                monster.spawn(Coordinate(coord.x, coord.y, 0), spot_id, WorldTick(0))
                monster_repo.save(monster)
            repository.save(physical_map)

            call_order = []
            def capture_order(actor_id_arg, map_agg, **kwargs):
                from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
                call_order.append(actor_id_arg)
                return BehaviorObservation(**{k: kwargs.get(k) for k in (
                    "visible_threats", "visible_hostiles", "selected_target", "skill_context",
                    "growth_context", "target_context", "pack_rally_coordinate", "current_tick",
                ) if k in kwargs})

            with mock.patch.object(service._behavior_service, "build_observation", side_effect=capture_order):
                service.tick()

            assert len(call_order) == 3
            assert call_order[0] == near_p1_id
            assert call_order[1] == near_p2_id
            assert call_order[2] == mid_id

        def test_single_actor_no_player_on_map(self, setup_service):
            """プレイヤーがいないマップではスポットが凍結され build_observation は呼ばれないこと"""
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)
            actor_id = WorldObjectId(1)
            physical_map.add_object(WorldObject(
                actor_id, Coordinate(2, 2), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(patrol_points=[Coordinate(2, 2), Coordinate(2, 3)]),
            ))
            repository.save(physical_map)

            call_count = [0]
            def count_calls(actor_id_arg, map_agg, **kwargs):
                call_count[0] += 1
                return BehaviorAction.move(Coordinate(2, 3))

            with mock.patch.object(service._behavior_service, "build_observation", side_effect=count_calls):
                service.tick()

            assert call_count[0] == 0

        def test_busy_actors_skipped_regardless_of_execution_order(self, setup_service):
            """実行順ソート後も、Busy なモンスターは build_observation が呼ばれずスキップされること"""
            service, _, repository, _, _, _, _, _, monster_repo, skill_loadout_repo = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)

            physical_map.add_object(WorldObject(
                WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(100)),
            ))
            near_id = WorldObjectId(1)
            far_busy_id = WorldObjectId(2)
            template = MonsterTemplate(
                template_id=MonsterTemplateId(1),
                name="M",
                base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
                reward_info=RewardInfo(0, 0),
                respawn_info=RespawnInfo(1, True),
                race=Race.HUMAN,
                faction=MonsterFactionEnum.ENEMY,
                description="M",
                skill_ids=[],
            )
            for oid, coord, busy in [(near_id, Coordinate(1, 0), None), (far_busy_id, Coordinate(3, 0), WorldTick(999))]:
                physical_map.add_object(WorldObject(
                    oid, coord, ObjectTypeEnum.NPC,
                    component=AutonomousBehaviorComponent(
                        patrol_points=[coord, coord],
                    ),
                    busy_until=busy,
                ))
                loadout = SkillLoadoutAggregate.create(SkillLoadoutId.create(oid.value), 1, 10, 10)
                skill_loadout_repo.save(loadout)
                monster = MonsterAggregate.create(MonsterId(oid.value), template, oid, skill_loadout=loadout)
                monster.spawn(Coordinate(coord.x, coord.y, 0), spot_id, WorldTick(0))
                monster_repo.save(monster)
            repository.save(physical_map)

            called_ids = []
            def capture_called(actor_id_arg, map_agg, **kwargs):
                from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
                called_ids.append(actor_id_arg)
                return BehaviorObservation(**{k: kwargs.get(k) for k in (
                    "visible_threats", "visible_hostiles", "selected_target", "skill_context",
                    "growth_context", "target_context", "pack_rally_coordinate", "current_tick",
                ) if k in kwargs})

            with mock.patch.object(service._behavior_service, "build_observation", side_effect=capture_called):
                service.tick()

            assert near_id in called_ids
            assert far_busy_id not in called_ids

        def test_empty_actors_no_crash(self, setup_service):
            """アクターが0体のマップ（プレイヤーもいない）でも build_observation が呼ばれず正常終了すること"""
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(3) for y in range(3)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)
            repository.save(physical_map)

            call_count = [0]
            def count_calls(actor_id_arg, map_agg, **kwargs):
                call_count[0] += 1
                return BehaviorAction.wait()

            with mock.patch.object(service._behavior_service, "build_observation", side_effect=count_calls):
                service.tick()

            assert call_count[0] == 0

        def test_player_only_map_execution_order(self, setup_service):
            """プレイヤーのみがいるマップではモンスターがいないため build_observation は呼ばれないこと"""
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)
            physical_map.add_object(WorldObject(
                WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(100)),
            ))
            repository.save(physical_map)

            call_order = []
            def capture_order(actor_id_arg, map_agg, **kwargs):
                call_order.append(actor_id_arg)
                return BehaviorAction.wait()

            with mock.patch.object(service._behavior_service, "build_observation", side_effect=capture_order):
                service.tick()

            assert len(call_order) == 0

    class TestActiveSpotFreeze:
        """スポット単位凍結（プレイヤーが存在するマップでのみ逐次更新）の正常・境界・異常系"""

        def test_only_active_spot_gets_build_observation_and_save(self, setup_service):
            """プレイヤーがいるスポットのみモンスターに build_observation が呼ばれ、そのスポットのみ save されること"""
            service, _, repository, _, _, _, _, _, monster_repo, skill_loadout_repo = setup_service
            spot_a = SpotId(1)
            spot_b = SpotId(2)
            tiles_5x5 = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
            map_a = PhysicalMapAggregate.create(spot_a, tiles_5x5)
            map_b = PhysicalMapAggregate.create(spot_b, tiles_5x5)
            map_a.add_object(WorldObject(
                WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(100)),
            ))
            map_a.add_object(WorldObject(
                WorldObjectId(1), Coordinate(1, 1), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(patrol_points=[Coordinate(1, 1), Coordinate(1, 2)]),
            ))
            map_b.add_object(WorldObject(
                WorldObjectId(2), Coordinate(2, 2), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(patrol_points=[Coordinate(2, 2), Coordinate(2, 3)]),
            ))
            repository.save(map_a)
            repository.save(map_b)

            template = MonsterTemplate(
                template_id=MonsterTemplateId(1),
                name="M",
                base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
                reward_info=RewardInfo(0, 0),
                respawn_info=RespawnInfo(1, True),
                race=Race.HUMAN,
                faction=MonsterFactionEnum.ENEMY,
                description="M",
                skill_ids=[],
            )
            for oid, spot_id, coord in [(1, spot_a, Coordinate(1, 1)), (2, spot_b, Coordinate(2, 2))]:
                loadout = SkillLoadoutAggregate.create(SkillLoadoutId.create(oid), 1, 10, 10)
                skill_loadout_repo.save(loadout)
                monster = MonsterAggregate.create(MonsterId(oid), template, WorldObjectId(oid), skill_loadout=loadout)
                monster.spawn(Coordinate(coord.x, coord.y, 0), spot_id, WorldTick(0))
                monster_repo.save(monster)

            build_observation_calls = []
            def capture_build(actor_id_arg, map_agg, **kwargs):
                from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
                build_observation_calls.append((actor_id_arg, map_agg.spot_id))
                return BehaviorObservation(**{k: kwargs.get(k) for k in (
                    "visible_threats", "visible_hostiles", "selected_target", "skill_context",
                    "growth_context", "target_context", "pack_rally_coordinate", "current_tick",
                ) if k in kwargs})

            save_calls = []
            original_save = repository.save
            def capture_save(physical_map):
                save_calls.append(physical_map.spot_id)
                return original_save(physical_map)

            with mock.patch.object(service._behavior_service, "build_observation", side_effect=capture_build):
                with mock.patch.object(service._physical_map_repository, "save", side_effect=capture_save):
                    service.tick()

            assert all(spot_id == spot_a for _, spot_id in build_observation_calls)
            assert len(build_observation_calls) == 1
            assert save_calls == [spot_a]

        def test_no_player_on_any_map_no_build_observation_no_save(self, setup_service):
            """全マップにプレイヤーがいない場合、build_observation も save も呼ばれないこと"""
            service, _, repository, _, _, _, _, _, _, _ = setup_service
            spot_a = SpotId(10)
            spot_b = SpotId(20)
            tiles = [Tile(Coordinate(0, 0), TerrainType.grass())]
            map_a = PhysicalMapAggregate.create(spot_a, tiles)
            map_b = PhysicalMapAggregate.create(spot_b, tiles)
            map_a.add_object(WorldObject(
                WorldObjectId(1), Coordinate(0, 0), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(patrol_points=[Coordinate(0, 0)]),
            ))
            map_b.add_object(WorldObject(
                WorldObjectId(2), Coordinate(0, 0), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(patrol_points=[Coordinate(0, 0)]),
            ))
            repository.save(map_a)
            repository.save(map_b)

            build_observation_count = [0]
            save_count = [0]
            def count_build_observation(*args, **kwargs):
                from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
                build_observation_count[0] += 1
                return BehaviorObservation()
            original_save = repository.save
            def count_save(physical_map):
                save_count[0] += 1
                return original_save(physical_map)

            with mock.patch.object(service._behavior_service, "build_observation", side_effect=count_build_observation):
                with mock.patch.object(service._physical_map_repository, "save", side_effect=count_save):
                    service.tick()

            assert build_observation_count[0] == 0
            assert save_count[0] == 0

        def test_both_spots_with_players_both_updated(self, setup_service):
            """複数スポットにそれぞれプレイヤーとモンスターがいる場合、両方のスポットで build_observation と save が行われること"""
            service, _, repository, _, _, _, _, _, monster_repo, skill_loadout_repo = setup_service
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
            map_a.add_object(WorldObject(
                WorldObjectId(1), Coordinate(1, 0), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(patrol_points=[Coordinate(1, 0)]),
            ))
            map_b.add_object(WorldObject(
                WorldObjectId(2), Coordinate(1, 0), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(patrol_points=[Coordinate(1, 0)]),
            ))
            repository.save(map_a)
            repository.save(map_b)

            template = MonsterTemplate(
                template_id=MonsterTemplateId(1),
                name="M",
                base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
                reward_info=RewardInfo(0, 0),
                respawn_info=RespawnInfo(1, True),
                race=Race.HUMAN,
                faction=MonsterFactionEnum.ENEMY,
                description="M",
                skill_ids=[],
            )
            for oid, spot_id in [(1, spot_a), (2, spot_b)]:
                loadout = SkillLoadoutAggregate.create(SkillLoadoutId.create(oid), 1, 10, 10)
                skill_loadout_repo.save(loadout)
                monster = MonsterAggregate.create(MonsterId(oid), template, WorldObjectId(oid), skill_loadout=loadout)
                monster.spawn(Coordinate(1, 0, 0), spot_id, WorldTick(0))
                monster_repo.save(monster)

            build_observation_spot_ids = []
            def capture_spot(actor_id_arg, map_agg, **kwargs):
                from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
                build_observation_spot_ids.append(map_agg.spot_id)
                return BehaviorObservation(**{k: kwargs.get(k) for k in (
                    "visible_threats", "visible_hostiles", "selected_target", "skill_context",
                    "growth_context", "target_context", "pack_rally_coordinate", "current_tick",
                ) if k in kwargs})

            save_spot_ids = []
            original_save = repository.save
            def capture_save(physical_map):
                save_spot_ids.append(physical_map.spot_id)
                return original_save(physical_map)

            with mock.patch.object(service._behavior_service, "build_observation", side_effect=capture_spot):
                with mock.patch.object(service._physical_map_repository, "save", side_effect=capture_save):
                    service.tick()

            assert set(build_observation_spot_ids) == {spot_a, spot_b}
            assert set(save_spot_ids) == {spot_a, spot_b}

        def test_inactive_spot_actors_never_get_build_observation(self, setup_service):
            """プレイヤーがいないスポットのモンスターには build_observation が一度も呼ばれないこと"""
            service, _, repository, _, _, _, _, _, monster_repo, skill_loadout_repo = setup_service
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
                component=AutonomousBehaviorComponent(patrol_points=[Coordinate(1, 0), Coordinate(1, 1)]),
            ))
            npc_on_inactive_id = WorldObjectId(2)
            map_inactive.add_object(WorldObject(
                npc_on_inactive_id, Coordinate(2, 2), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(patrol_points=[Coordinate(2, 2), Coordinate(2, 3)]),
            ))
            repository.save(map_active)
            repository.save(map_inactive)

            template = MonsterTemplate(
                template_id=MonsterTemplateId(1),
                name="M",
                base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
                reward_info=RewardInfo(0, 0),
                respawn_info=RespawnInfo(1, True),
                race=Race.HUMAN,
                faction=MonsterFactionEnum.ENEMY,
                description="M",
                skill_ids=[],
            )
            for oid, spot_id, coord in [(1, spot_active, Coordinate(1, 0)), (2, spot_inactive, Coordinate(2, 2))]:
                loadout = SkillLoadoutAggregate.create(SkillLoadoutId.create(oid), 1, 10, 10)
                skill_loadout_repo.save(loadout)
                monster = MonsterAggregate.create(MonsterId(oid), template, WorldObjectId(oid), skill_loadout=loadout)
                monster.spawn(Coordinate(coord.x, coord.y, 0), spot_id, WorldTick(0))
                monster_repo.save(monster)

            build_observation_actor_ids = []
            def capture_actor(actor_id_arg, map_agg, **kwargs):
                from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
                build_observation_actor_ids.append(actor_id_arg)
                return BehaviorObservation(**{k: kwargs.get(k) for k in (
                    "visible_threats", "visible_hostiles", "selected_target", "skill_context",
                    "growth_context", "target_context", "pack_rally_coordinate", "current_tick",
                ) if k in kwargs})

            with mock.patch.object(service._behavior_service, "build_observation", side_effect=capture_actor):
                service.tick()

            assert npc_on_inactive_id not in build_observation_actor_ids
            assert WorldObjectId(1) in build_observation_actor_ids

        def test_single_map_with_player_behaves_as_before(self, setup_service):
            """プレイヤーとモンスターが1体いるマップでは decide → 移動イベント → ハンドラで座標が更新されること"""
            service, _, repository, _, _, _, _, _, monster_repo, skill_loadout_repo = setup_service
            spot_id = SpotId(1)
            tiles = [Tile(Coordinate(x, y), TerrainType.grass()) for x in range(5) for y in range(5)]
            physical_map = PhysicalMapAggregate.create(spot_id, tiles)
            actor_id = WorldObjectId(1)
            physical_map.add_object(WorldObject(
                WorldObjectId(100), Coordinate(0, 0), ObjectTypeEnum.PLAYER,
                component=ActorComponent(player_id=PlayerId(100)),
            ))
            physical_map.add_object(WorldObject(
                actor_id, Coordinate(2, 2), ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(patrol_points=[Coordinate(2, 2), Coordinate(2, 3)]),
            ))
            repository.save(physical_map)

            loadout = SkillLoadoutAggregate.create(SkillLoadoutId.create(1), 1, 10, 10)
            skill_loadout_repo.save(loadout)
            template = MonsterTemplate(
                template_id=MonsterTemplateId(1),
                name="M",
                base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
                reward_info=RewardInfo(0, 0),
                respawn_info=RespawnInfo(1, True),
                race=Race.HUMAN,
                faction=MonsterFactionEnum.ENEMY,
                description="M",
                skill_ids=[],
            )
            monster = MonsterAggregate.create(MonsterId(1), template, actor_id, skill_loadout=loadout)
            monster.spawn(Coordinate(2, 2, 0), spot_id, WorldTick(0))
            monster_repo.save(monster)

            # リゾルバが MOVE を返すようにモック（decide → MonsterDecidedToMoveEvent → ハンドラで移動）
            move_action = BehaviorAction.move(Coordinate(2, 3))
            fake_resolver = mock.Mock()
            fake_resolver.resolve_action.return_value = move_action
            with mock.patch.object(service, "_monster_action_resolver_factory", return_value=fake_resolver):
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
        """活動時間帯でない自律アクター（モンスター）は build_observation をスキップするテスト"""

        def test_nocturnal_actor_skipped_during_day(self, setup_service):
            """昼の時間帯では夜行性モンスターには build_observation が呼ばれないこと"""
            service, time_provider, repository, _, _, _, _, _, monster_repo, skill_loadout_repo = setup_service
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
            nocturnal_id = WorldObjectId(1)
            physical_map.add_object(WorldObject(
                nocturnal_id,
                Coordinate(2, 2),
                ObjectTypeEnum.NPC,
                component=AutonomousBehaviorComponent(
                    patrol_points=[Coordinate(2, 2), Coordinate(2, 3)],
                    active_time=ActiveTimeType.NOCTURNAL,
                ),
            ))
            repository.save(physical_map)

            loadout = SkillLoadoutAggregate.create(SkillLoadoutId.create(1), 1, 10, 10)
            skill_loadout_repo.save(loadout)
            template = MonsterTemplate(
                template_id=MonsterTemplateId(1),
                name="M",
                base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
                reward_info=RewardInfo(0, 0),
                respawn_info=RespawnInfo(1, True),
                race=Race.HUMAN,
                faction=MonsterFactionEnum.ENEMY,
                description="M",
                skill_ids=[],
            )
            monster = MonsterAggregate.create(MonsterId(1), template, nocturnal_id, skill_loadout=loadout)
            monster.spawn(Coordinate(2, 2, 0), spot_id, WorldTick(0))
            monster_repo.save(monster)

            build_observation_actor_ids = []
            def capture_actor(actor_id_arg, map_agg, **kwargs):
                from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
                build_observation_actor_ids.append(actor_id_arg)
                return BehaviorObservation()

            with mock.patch.object(service._behavior_service, "build_observation", side_effect=capture_actor):
                service.tick()

            assert nocturnal_id not in build_observation_actor_ids

        def test_diurnal_actor_acts_during_day(self, setup_service):
            """昼の時間帯では昼行性モンスターには build_observation が呼ばれること"""
            service, time_provider, repository, _, _, _, _, _, monster_repo, skill_loadout_repo = setup_service
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
                    patrol_points=[Coordinate(2, 2), Coordinate(2, 3)],
                    active_time=ActiveTimeType.DIURNAL,
                ),
            ))
            repository.save(physical_map)

            loadout = SkillLoadoutAggregate.create(SkillLoadoutId.create(1), 1, 10, 10)
            skill_loadout_repo.save(loadout)
            template = MonsterTemplate(
                template_id=MonsterTemplateId(1),
                name="M",
                base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
                reward_info=RewardInfo(0, 0),
                respawn_info=RespawnInfo(1, True),
                race=Race.HUMAN,
                faction=MonsterFactionEnum.ENEMY,
                description="M",
                skill_ids=[],
            )
            monster = MonsterAggregate.create(MonsterId(1), template, diurnal_id, skill_loadout=loadout)
            monster.spawn(Coordinate(2, 2, 0), spot_id, WorldTick(0))
            monster_repo.save(monster)

            build_observation_actor_ids = []
            def capture_actor(actor_id_arg, map_agg, **kwargs):
                from ai_rpg_world.domain.world.value_object.behavior_observation import BehaviorObservation
                build_observation_actor_ids.append(actor_id_arg)
                return BehaviorObservation()

            with mock.patch.object(service._behavior_service, "build_observation", side_effect=capture_actor):
                service.tick()

            assert diurnal_id in build_observation_actor_ids

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
                reward_info=RewardInfo(10, 10, 1),
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
