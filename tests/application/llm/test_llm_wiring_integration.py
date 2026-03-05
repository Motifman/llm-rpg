"""
ブートストラップ契約の統合テスト。

create_llm_agent_wiring の返り値 (observation_registry, llm_turn_trigger) を
EventHandlerComposition および WorldSimulationApplicationService に渡したときに
契約どおり動作することを検証する。正常・例外の両方を網羅する。
"""

import pytest
import unittest.mock as mock
from unittest.mock import MagicMock, patch

from ai_rpg_world.application.llm.wiring import create_llm_agent_wiring
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
    IObservationFormatter,
)
from ai_rpg_world.application.llm.contracts.interfaces import ILlmTurnTrigger
from ai_rpg_world.application.world.services.world_query_service import WorldQueryService
from ai_rpg_world.application.world.services.movement_service import MovementApplicationService
from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory
from ai_rpg_world.domain.player.repository.player_profile_repository import PlayerProfileRepository
from ai_rpg_world.domain.player.repository.player_status_repository import PlayerStatusRepository
from ai_rpg_world.domain.world.repository.physical_map_repository import PhysicalMapRepository
from ai_rpg_world.infrastructure.events.event_handler_composition import EventHandlerComposition
from ai_rpg_world.infrastructure.events.event_handler_profile import EventHandlerProfile
from ai_rpg_world.infrastructure.events.observation_event_handler_registry import (
    ObservationEventHandlerRegistry,
)


def _minimal_wiring_deps():
    """create_llm_agent_wiring に渡す最小限のモック依存を返す。"""
    uow_factory = MagicMock(spec=UnitOfWorkFactory)
    uow_factory.create.return_value = MagicMock()
    uow_factory.create.return_value.__enter__ = MagicMock(return_value=MagicMock())
    uow_factory.create.return_value.__exit__ = MagicMock(return_value=False)
    world_query = MagicMock(spec=WorldQueryService)
    world_query.get_player_current_state = MagicMock(return_value=None)
    movement = MagicMock(spec=MovementApplicationService)
    movement.move_to_destination = MagicMock()
    movement.cancel_movement = MagicMock()
    return {
        "player_status_repository": MagicMock(spec=PlayerStatusRepository),
        "physical_map_repository": MagicMock(spec=PhysicalMapRepository),
        "world_query_service": world_query,
        "movement_service": movement,
        "player_profile_repository": MagicMock(spec=PlayerProfileRepository),
        "unit_of_work_factory": uow_factory,
    }


# ---------------------------------------------------------------------------
# EventHandlerComposition + observation_registry 契約
# ---------------------------------------------------------------------------


class TestBootstrapContractEventHandlerComposition:
    """ブートストラップ契約: observation_registry を EventHandlerComposition に渡す場合の統合テスト"""

    @pytest.fixture
    def event_publisher(self):
        """モックの EventPublisher"""
        return MagicMock()

    def test_registry_from_wiring_registers_handlers_when_composition_full(
        self, event_publisher
    ):
        """create_llm_agent_wiring の返り値 registry を Composition に渡し FULL で登録すると register_handlers が呼ばれる（正常）"""
        deps = _minimal_wiring_deps()
        registry, _ = create_llm_agent_wiring(**deps)
        assert isinstance(registry, ObservationEventHandlerRegistry)

        composition = EventHandlerComposition(
            gateway_handler=MagicMock(),
            map_interaction_registry=MagicMock(),
            observation_registry=registry,
        )
        with patch.object(
            registry, "register_handlers", wraps=registry.register_handlers
        ) as spy:
            composition.register_for_profile(event_publisher, EventHandlerProfile.FULL)
            spy.assert_called_once_with(event_publisher)

    def test_registry_from_wiring_is_used_by_composition_as_observation_registry(
        self, event_publisher
    ):
        """Composition に渡した registry が observation_registry として保持され FULL で使われる（正常）"""
        deps = _minimal_wiring_deps()
        registry, _ = create_llm_agent_wiring(**deps)
        composition = EventHandlerComposition(
            gateway_handler=MagicMock(),
            observation_registry=registry,
        )
        assert composition._observation_registry is registry
        with patch.object(registry, "register_handlers", wraps=registry.register_handlers) as spy:
            composition.register_for_profile(event_publisher, EventHandlerProfile.FULL)
            spy.assert_called_once()

    def test_register_for_profile_movement_only_does_not_call_observation_registry(
        self, event_publisher
    ):
        """MOVEMENT_ONLY のときは observation_registry.register_handlers は呼ばれない（境界）"""
        deps = _minimal_wiring_deps()
        registry, _ = create_llm_agent_wiring(**deps)
        composition = EventHandlerComposition(
            gateway_handler=MagicMock(),
            observation_registry=registry,
        )
        with patch.object(registry, "register_handlers", wraps=registry.register_handlers) as spy:
            composition.register_for_profile(
                event_publisher, EventHandlerProfile.MOVEMENT_ONLY
            )
            spy.assert_not_called()

    def test_register_for_profile_unknown_raises_value_error(self, event_publisher):
        """存在しないプロファイルで register_for_profile すると ValueError（例外）"""
        deps = _minimal_wiring_deps()
        registry, _ = create_llm_agent_wiring(**deps)
        composition = EventHandlerComposition(observation_registry=registry)
        with pytest.raises(ValueError, match="Unknown profile"):
            composition.register_for_profile(
                event_publisher,
                "unknown_profile",  # type: ignore[arg-type]
            )


# ---------------------------------------------------------------------------
# WorldSimulationApplicationService + llm_turn_trigger 契約
# ---------------------------------------------------------------------------


class TestBootstrapContractWorldSimulationService:
    """ブートストラップ契約: llm_turn_trigger を WorldSimulationApplicationService に渡す場合の統合テスト"""

    @pytest.fixture
    def service_with_llm_trigger(self):
        """create_llm_agent_wiring で取得した trigger を渡した WorldSimulationApplicationService を組み立てる。"""
        from ai_rpg_world.application.world.services.world_simulation_service import (
            WorldSimulationApplicationService,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_data_store import (
            InMemoryDataStore,
        )
        from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
            InMemoryUnitOfWork,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
            InMemoryPhysicalMapRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_weather_zone_repository import (
            InMemoryWeatherZoneRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
            InMemoryPlayerStatusRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_hit_box_repository import (
            InMemoryHitBoxRepository,
        )
        from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
            InMemoryGameTimeProvider,
        )
        from ai_rpg_world.domain.common.value_object import WorldTick
        from ai_rpg_world.domain.world.service.behavior_service import BehaviorService
        from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
        from ai_rpg_world.application.world.services.caching_pathfinding_service import (
            CachingPathfindingService,
        )
        from ai_rpg_world.domain.world.service.weather_config_service import (
            DefaultWeatherConfigService,
        )
        from ai_rpg_world.domain.world.service.world_time_config_service import (
            DefaultWorldTimeConfigService,
        )
        from ai_rpg_world.domain.combat.service.hit_box_config_service import (
            DefaultHitBoxConfigService,
        )
        from ai_rpg_world.domain.combat.service.hit_box_collision_service import (
            HitBoxCollisionDomainService,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_monster_aggregate_repository import (
            InMemoryMonsterAggregateRepository,
        )

        class _InMemorySkillLoadoutRepo:
            def __init__(self):
                self._data = {}

            def save(self, loadout):
                self._data[loadout.loadout_id] = loadout

            def find_by_id(self, loadout_id):
                return self._data.get(loadout_id)

        data_store = InMemoryDataStore()
        data_store.clear_all()
        time_provider = InMemoryGameTimeProvider(initial_tick=10)

        def create_uow():
            return InMemoryUnitOfWork(
                unit_of_work_factory=create_uow, data_store=data_store
            )

        uow, _event_publisher = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow,
            data_store=data_store,
        )
        repository = InMemoryPhysicalMapRepository(data_store, uow)
        weather_zone_repo = InMemoryWeatherZoneRepository(data_store, uow)
        player_status_repo = InMemoryPlayerStatusRepository(data_store, uow)
        hit_box_repo = InMemoryHitBoxRepository(data_store, uow)

        from ai_rpg_world.infrastructure.world.pathfinding.astar_pathfinding_strategy import (
            AStarPathfindingStrategy,
        )
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
        monster_repo = InMemoryMonsterAggregateRepository(data_store, uow)
        skill_loadout_repo = _InMemorySkillLoadoutRepo()

        from ai_rpg_world.domain.monster.service.monster_skill_execution_domain_service import (
            MonsterSkillExecutionDomainService,
        )
        from ai_rpg_world.domain.skill.service.skill_execution_service import (
            SkillExecutionDomainService,
        )
        from ai_rpg_world.domain.skill.service.skill_targeting_service import (
            SkillTargetingDomainService,
        )
        from ai_rpg_world.domain.skill.service.skill_to_hitbox_service import (
            SkillToHitBoxDomainService,
        )
        skill_execution_service = SkillExecutionDomainService(
            SkillTargetingDomainService(),
            SkillToHitBoxDomainService(),
        )
        monster_skill_execution_domain_service = MonsterSkillExecutionDomainService(
            skill_execution_service
        )
        from ai_rpg_world.domain.combat.service.hit_box_factory import HitBoxFactory
        from ai_rpg_world.domain.world.service.skill_selection_policy import (
            FirstInRangeSkillPolicy,
        )
        from ai_rpg_world.application.world.services.monster_action_resolver import (
            create_monster_action_resolver_factory,
        )
        from ai_rpg_world.application.world.handlers.monster_decided_to_move_handler import (
            MonsterDecidedToMoveHandler,
        )
        from ai_rpg_world.application.world.handlers.monster_decided_to_use_skill_handler import (
            MonsterDecidedToUseSkillHandler,
        )
        from ai_rpg_world.application.world.handlers.monster_decided_to_interact_handler import (
            MonsterDecidedToInteractHandler,
        )
        from ai_rpg_world.application.world.handlers.monster_fed_handler import (
            MonsterFedHandler,
        )
        from ai_rpg_world.infrastructure.events.monster_event_handler_registry import (
            MonsterEventHandlerRegistry,
        )

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
        ).register_handlers(_event_publisher)

        # create_llm_agent_wiring で trigger を取得（同一の repos を渡して契約どおりに組み立て）
        uow_factory = MagicMock(spec=UnitOfWorkFactory)
        uow_factory.create.return_value = uow
        wiring_deps = {
            "player_status_repository": player_status_repo,
            "physical_map_repository": repository,
            "world_query_service": MagicMock(spec=WorldQueryService),
            "movement_service": MagicMock(spec=MovementApplicationService),
            "player_profile_repository": MagicMock(spec=PlayerProfileRepository),
            "unit_of_work_factory": uow_factory,
        }
        _registry, llm_turn_trigger = create_llm_agent_wiring(**wiring_deps)
        assert isinstance(llm_turn_trigger, ILlmTurnTrigger)

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
            llm_turn_trigger=llm_turn_trigger,
        )
        return service, llm_turn_trigger, time_provider

    def test_tick_invokes_run_scheduled_turns_when_trigger_from_wiring_provided(
        self, service_with_llm_trigger
    ):
        """create_llm_agent_wiring の trigger を渡した Service で tick() すると run_scheduled_turns が 1 回呼ばれる（正常）"""
        service, trigger, _ = service_with_llm_trigger
        with patch.object(
            trigger, "run_scheduled_turns", wraps=trigger.run_scheduled_turns
        ) as spy:
            service.tick()
            spy.assert_called_once()

    def test_tick_advances_time_when_trigger_from_wiring_provided(
        self, service_with_llm_trigger
    ):
        """trigger を渡した Service でも tick() で時刻が進む（正常）"""
        service, _, time_provider = service_with_llm_trigger
        from ai_rpg_world.domain.common.value_object import WorldTick

        assert time_provider.get_current_tick() == WorldTick(10)
        service.tick()
        assert time_provider.get_current_tick() == WorldTick(11)

    def test_tick_when_trigger_raises_propagates_as_system_error(
        self, service_with_llm_trigger
    ):
        """llm_turn_trigger.run_scheduled_turns が例外を投げた場合、tick() は SystemErrorException でラップして伝播する（例外）"""
        from ai_rpg_world.application.common.exceptions import SystemErrorException

        service, trigger, _ = service_with_llm_trigger
        with patch.object(
            trigger, "run_scheduled_turns", side_effect=RuntimeError("trigger failed")
        ):
            with pytest.raises(SystemErrorException, match="tick failed") as exc_info:
                service.tick()
            assert exc_info.value.original_exception is not None
            assert "trigger failed" in str(exc_info.value.original_exception)


# ---------------------------------------------------------------------------
# create_llm_agent_wiring の入力検証（例外）
# ---------------------------------------------------------------------------


class TestBootstrapContractWiringValidation:
    """create_llm_agent_wiring の必須引数検証を統合テストで保証する"""

    @pytest.fixture
    def deps(self):
        return _minimal_wiring_deps()

    def test_player_status_repository_none_raises_type_error(self, deps):
        """player_status_repository が None のとき TypeError（必須引数検証の代表）"""
        deps["player_status_repository"] = None
        with pytest.raises(TypeError, match="player_status_repository must not be None"):
            create_llm_agent_wiring(**deps)

    def test_physical_map_repository_none_raises_type_error(self, deps):
        """physical_map_repository が None のとき TypeError"""
        deps["physical_map_repository"] = None
        with pytest.raises(TypeError, match="physical_map_repository must not be None"):
            create_llm_agent_wiring(**deps)

    def test_world_query_service_none_raises_type_error(self, deps):
        """world_query_service が None のとき TypeError"""
        deps["world_query_service"] = None
        with pytest.raises(TypeError, match="world_query_service must not be None"):
            create_llm_agent_wiring(**deps)

    def test_movement_service_none_raises_type_error(self, deps):
        """movement_service が None のとき TypeError"""
        deps["movement_service"] = None
        with pytest.raises(TypeError, match="movement_service must not be None"):
            create_llm_agent_wiring(**deps)

    def test_player_profile_repository_none_raises_type_error(self, deps):
        """player_profile_repository が None のとき TypeError"""
        deps["player_profile_repository"] = None
        with pytest.raises(TypeError, match="player_profile_repository must not be None"):
            create_llm_agent_wiring(**deps)

    def test_unit_of_work_factory_none_raises_type_error(self, deps):
        """unit_of_work_factory が None のとき TypeError"""
        deps["unit_of_work_factory"] = None
        with pytest.raises(TypeError, match="unit_of_work_factory must not be None"):
            create_llm_agent_wiring(**deps)

    def test_env_llm_client_unknown_raises_value_error(self, deps, monkeypatch):
        """llm_client 未指定かつ LLM_CLIENT が stub/litellm 以外のとき ValueError"""
        monkeypatch.setenv("LLM_CLIENT", "unknown")
        with pytest.raises(ValueError, match="LLM_CLIENT must be one of"):
            create_llm_agent_wiring(**deps)


# ---------------------------------------------------------------------------
# 契約の一貫性（返り値の型・契約履行の前提）
# ---------------------------------------------------------------------------


class TestBootstrapContractReturnValues:
    """create_llm_agent_wiring の返り値が契約で期待する型・インターフェースを満たすことを検証する"""

    def test_returns_tuple_registry_and_trigger(self):
        """返り値は (ObservationEventHandlerRegistry, ILlmTurnTrigger) のタプル（正常）"""
        deps = _minimal_wiring_deps()
        result = create_llm_agent_wiring(**deps)
        assert isinstance(result, tuple)
        assert len(result) == 2
        registry, trigger = result
        assert isinstance(registry, ObservationEventHandlerRegistry)
        assert isinstance(trigger, ILlmTurnTrigger)

    def test_registry_has_register_handlers(self):
        """返された registry は register_handlers(event_publisher) を持つ（契約前提）"""
        deps = _minimal_wiring_deps()
        registry, _ = create_llm_agent_wiring(**deps)
        assert hasattr(registry, "register_handlers")
        assert callable(registry.register_handlers)

    def test_trigger_has_run_scheduled_turns(self):
        """返された trigger は run_scheduled_turns() を持つ（契約前提）"""
        deps = _minimal_wiring_deps()
        _, trigger = create_llm_agent_wiring(**deps)
        assert hasattr(trigger, "run_scheduled_turns")
        assert callable(trigger.run_scheduled_turns)

    def test_trigger_run_scheduled_turns_empty_does_not_raise(self):
        """スケジュール済みがいない状態で run_scheduled_turns を呼んでも例外が出ない（境界）"""
        deps = _minimal_wiring_deps()
        _, trigger = create_llm_agent_wiring(**deps)
        trigger.run_scheduled_turns()

    def test_optional_observation_formatter_injected_into_handler(self):
        """observation_formatter を渡した場合、返された registry のハンドラがそのフォーマッタを保持する（正常）"""
        custom_formatter = MagicMock(spec=IObservationFormatter)
        deps = _minimal_wiring_deps()
        deps["observation_formatter"] = custom_formatter
        registry, _ = create_llm_agent_wiring(**deps)
        assert registry._handler._formatter is custom_formatter

    def test_optional_observation_buffer_injected_into_handler(self):
        """observation_buffer を渡した場合、返された registry のハンドラがそのバッファを保持する（正常）"""
        custom_buffer = MagicMock(spec=IObservationContextBuffer)
        deps = _minimal_wiring_deps()
        deps["observation_buffer"] = custom_buffer
        registry, _ = create_llm_agent_wiring(**deps)
        assert registry._handler._buffer is custom_buffer
