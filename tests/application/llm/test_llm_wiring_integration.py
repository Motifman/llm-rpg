"""
ブートストラップ契約の統合テスト。

create_llm_agent_wiring の返り値 (observation_registry, llm_turn_trigger) を
EventHandlerComposition および WorldSimulationApplicationService に渡したときに
契約どおり動作することを検証する。正常・例外の両方を網羅する。
"""

import json
import pytest
import unittest.mock as mock
from unittest.mock import MagicMock, patch

from ai_rpg_world.application.llm.bootstrap import compose_llm_runtime, ComposeLlmRuntimeResult
from ai_rpg_world.application.llm.wiring import create_llm_agent_wiring
from ai_rpg_world.presentation.player_pursuit_runtime import (
    PlayerPursuitRuntimeResult,
    compose_player_pursuit_runtime,
)
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
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
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
        # 観測にゲーム内時刻を付与するため、シミュレーションと同じ time_provider と world_time_config を渡す
        world_time_config = DefaultWorldTimeConfigService(ticks_per_day=24)
        uow_factory = MagicMock(spec=UnitOfWorkFactory)
        uow_factory.create.return_value = uow
        wiring_deps = {
            "player_status_repository": player_status_repo,
            "physical_map_repository": repository,
            "world_query_service": MagicMock(spec=WorldQueryService),
            "movement_service": MagicMock(spec=MovementApplicationService),
            "player_profile_repository": MagicMock(spec=PlayerProfileRepository),
            "unit_of_work_factory": uow_factory,
            "game_time_provider": time_provider,
            "world_time_config_service": world_time_config,
        }
        wiring_result = create_llm_agent_wiring(**wiring_deps)
        assert isinstance(wiring_result.llm_turn_trigger, ILlmTurnTrigger)

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
            world_time_config_service=world_time_config,
            monster_action_resolver_factory=monster_action_resolver_factory,
            llm_turn_trigger=wiring_result.llm_turn_trigger,
            reflection_runner=wiring_result.reflection_runner,
        )
        return service, wiring_result.llm_turn_trigger, time_provider

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

    def test_returns_wiring_result_with_registry_and_trigger(self):
        """返り値は unpacking で (registry, trigger) が取得でき、reflection_runner も持つ（正常）"""
        deps = _minimal_wiring_deps()
        result = create_llm_agent_wiring(**deps)
        registry, trigger = result
        assert isinstance(registry, ObservationEventHandlerRegistry)
        assert isinstance(trigger, ILlmTurnTrigger)
        assert hasattr(result, "observation_registry")
        assert hasattr(result, "llm_turn_trigger")
        assert hasattr(result, "reflection_runner")

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


# ---------------------------------------------------------------------------
# compose_llm_runtime bootstrap seam
# ---------------------------------------------------------------------------


class TestComposeLlmRuntimeBootstrapSeam:
    """compose_llm_runtime のブートストラップ窓口テスト"""

    def test_compose_llm_runtime_returns_wiring_result_without_builders(self):
        """composition_builder / service_builder なしで呼ぶと wiring_result のみ返る"""
        deps = _minimal_wiring_deps()
        result = compose_llm_runtime(**deps)
        assert isinstance(result, ComposeLlmRuntimeResult)
        assert result.wiring_result is not None
        assert result.observation_registry is result.wiring_result.observation_registry
        assert result.llm_turn_trigger is result.wiring_result.llm_turn_trigger
        assert result.event_handler_composition is None
        assert result.world_simulation_service is None

    def test_compose_llm_runtime_with_builders_produces_composition_and_service(self):
        """composition_builder / service_builder を渡すと composition と service が生成される"""
        deps = _minimal_wiring_deps()
        compositions = []

        def comp_builder(registry):
            comp = EventHandlerComposition(
                gateway_handler=MagicMock(),
                observation_registry=registry,
            )
            compositions.append(comp)
            return comp

        services = []

        def svc_builder(trigger, reflection_runner):
            svc = MagicMock()
            svc._llm_turn_trigger = trigger
            svc._reflection_runner = reflection_runner
            services.append(svc)
            return svc

        result = compose_llm_runtime(
            composition_builder=comp_builder,
            service_builder=svc_builder,
            **deps,
        )
        assert result.event_handler_composition is compositions[0]
        assert result.event_handler_composition._observation_registry is result.observation_registry
        assert result.world_simulation_service is services[0]
        assert result.world_simulation_service._llm_turn_trigger is result.llm_turn_trigger


class TestComposePlayerPursuitRuntime:
    """player pursuit runtime の authoritative bootstrap 契約"""

    def test_compose_player_pursuit_runtime_requires_both_pursuit_services(self):
        deps = _minimal_wiring_deps()

        with pytest.raises(TypeError, match="pursuit_command_service must not be None"):
            compose_player_pursuit_runtime(
                pursuit_command_service=None,
                pursuit_continuation_service=MagicMock(),
                **deps,
            )

        with pytest.raises(
            TypeError, match="pursuit_continuation_service must not be None"
        ):
            compose_player_pursuit_runtime(
                pursuit_command_service=MagicMock(),
                pursuit_continuation_service=None,
                **deps,
            )

    def test_compose_player_pursuit_runtime_builds_composition_and_service(self):
        deps = _minimal_wiring_deps()
        pursuit_command_service = MagicMock()
        pursuit_continuation_service = MagicMock()
        compositions = []
        services = []

        def comp_builder(registry):
            comp = EventHandlerComposition(
                gateway_handler=MagicMock(),
                observation_registry=registry,
            )
            compositions.append(comp)
            return comp

        def svc_builder(continuation_service, trigger, reflection_runner):
            svc = MagicMock()
            svc._pursuit_continuation_service = continuation_service
            svc._llm_turn_trigger = trigger
            svc._reflection_runner = reflection_runner
            services.append(svc)
            return svc

        result = compose_player_pursuit_runtime(
            pursuit_command_service=pursuit_command_service,
            pursuit_continuation_service=pursuit_continuation_service,
            composition_builder=comp_builder,
            service_builder=svc_builder,
            **deps,
        )

        assert isinstance(result, PlayerPursuitRuntimeResult)
        assert result.pursuit_command_service is pursuit_command_service
        assert result.pursuit_continuation_service is pursuit_continuation_service
        assert result.pursuit_enabled is True
        assert result.event_handler_composition is compositions[0]
        assert result.event_handler_composition._observation_registry is result.observation_registry
        assert result.world_simulation_service is services[0]
        assert (
            result.world_simulation_service._pursuit_continuation_service
            is pursuit_continuation_service
        )
        assert result.world_simulation_service._llm_turn_trigger is result.llm_turn_trigger

    def test_compose_player_pursuit_runtime_exposes_pursuit_tools_on_live_path(self):
        deps = _minimal_wiring_deps()
        pursuit_command_service = MagicMock()
        pursuit_continuation_service = MagicMock()

        result = compose_player_pursuit_runtime(
            pursuit_command_service=pursuit_command_service,
            pursuit_continuation_service=pursuit_continuation_service,
            **deps,
        )

        tool_mapper = result.llm_turn_trigger._turn_runner._orchestrator._tool_command_mapper
        assert tool_mapper._pursuit_service is pursuit_command_service


# ---------------------------------------------------------------------------
# SQLite memory restore guarantee
# ---------------------------------------------------------------------------


class TestSqliteMemoryRestore:
    """memory_db_path 経由の再起動復元契約を統合テストで保証する"""

    def test_wiring_recreate_restores_episode_from_sqlite(self, tmp_path):
        """episode を書き込んだ後に wiring を再生成し、復元できること"""
        from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
        from ai_rpg_world.application.llm.contracts.dtos import EpisodeMemoryEntry
        from datetime import datetime
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId

        db_path = tmp_path / "restore_test.db"
        deps = _minimal_wiring_deps()
        deps["memory_db_path"] = str(db_path)
        deps["llm_client"] = StubLlmClient()

        episode_entry = EpisodeMemoryEntry(
            id="ep-restore-test",
            context_summary="テスト",
            action_taken="移動した",
            outcome_summary="成功",
            entity_ids=(),
            location_id=None,
            timestamp=datetime.now(),
            importance="medium",
            surprise=False,
            recall_count=0,
        )

        # 1st wiring: add episode
        wiring1 = create_llm_agent_wiring(**deps)
        episode_store1 = wiring1.llm_turn_trigger._turn_runner._orchestrator._episode_memory_store
        episode_store1.add(PlayerId(1), episode_entry)
        del wiring1

        # 2nd wiring: same path, verify restore
        wiring2 = create_llm_agent_wiring(**deps)
        episode_store2 = wiring2.llm_turn_trigger._turn_runner._orchestrator._episode_memory_store
        recent = episode_store2.get_recent(PlayerId(1), limit=10)
        assert len(recent) >= 1
        assert any(e.id == "ep-restore-test" and e.action_taken == "移動した" for e in recent)


# ---------------------------------------------------------------------------
# E2E: domain event -> observation buffer -> schedule_turn -> run_scheduled_turns -> episode memory save
# ---------------------------------------------------------------------------


class TestEventToEpisodeMemoryE2E:
    """LLMイベント起点フローのE2E: ドメインイベント発行からエピソード記憶保存までの一連の流れを検証する"""

    def test_domain_event_triggers_observation_schedule_turn_and_episode_memory_save(self):
        """
        PlayerDownedEvent 発行 → 観測バッファ追記 → schedule_turn → run_scheduled_turns
        → ツール実行 → episode memory save の流れが動作すること。
        注入した episode_memory_store にエピソードが保存されていることを検証する。
        """
        from ai_rpg_world.application.llm.services.in_memory_episode_memory_store import (
            InMemoryEpisodeMemoryStore,
        )
        from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
        from ai_rpg_world.application.llm.services.llm_player_resolver import (
            SetBasedLlmPlayerResolver,
        )
        from ai_rpg_world.application.llm.services.sliding_window_memory import (
            DefaultSlidingWindowMemory,
        )
        from ai_rpg_world.domain.player.event.status_events import (
            PlayerDownedEvent,
            PlayerLocationChangedEvent,
        )
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
        from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
            PlayerProfileAggregate,
        )
        from ai_rpg_world.domain.player.enum.player_enum import ControlType
        from ai_rpg_world.domain.player.value_object.player_name import PlayerName
        from ai_rpg_world.domain.world.entity.spot import Spot
        from ai_rpg_world.infrastructure.repository.in_memory_data_store import (
            InMemoryDataStore,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import (
            InMemoryPlayerProfileRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
            InMemoryPlayerStatusRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
            InMemoryPhysicalMapRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_spot_repository import (
            InMemorySpotRepository,
        )

        data_store = InMemoryDataStore()
        data_store.clear_all()

        def create_uow():
            return InMemoryUnitOfWork(
                unit_of_work_factory=create_uow, data_store=data_store
            )

        uow, event_publisher = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow,
            data_store=data_store,
        )

        profile_repo = InMemoryPlayerProfileRepository(data_store, None)
        spot_repo = InMemorySpotRepository(data_store, None)
        profile = PlayerProfileAggregate.create(
            PlayerId(1), PlayerName("E2EPlayer"), control_type=ControlType.LLM
        )
        profile_repo.save(profile)
        spot_repo.save(Spot(SpotId(1), "SpotA", "A"))
        spot_repo.save(Spot(SpotId(2), "SpotB", "B"))

        player_status_repo = InMemoryPlayerStatusRepository(data_store, None)
        physical_map_repo = InMemoryPhysicalMapRepository(data_store, None)
        world_query = MagicMock(spec=WorldQueryService)
        world_query.get_player_current_state = MagicMock(return_value=None)
        movement = MagicMock(spec=MovementApplicationService)
        movement.move_to_destination = MagicMock()
        movement.cancel_movement = MagicMock()

        episode_memory_store = InMemoryEpisodeMemoryStore()
        sliding_window = DefaultSlidingWindowMemory(max_entries_per_player=1)

        uow_factory = MagicMock(spec=UnitOfWorkFactory)
        uow_factory.create.return_value = uow

        wiring_result = create_llm_agent_wiring(
            player_status_repository=player_status_repo,
            physical_map_repository=physical_map_repo,
            world_query_service=world_query,
            movement_service=movement,
            player_profile_repository=profile_repo,
            unit_of_work_factory=uow_factory,
            spot_repository=spot_repo,
            episode_memory_store=episode_memory_store,
            sliding_window_memory=sliding_window,
            llm_player_resolver=SetBasedLlmPlayerResolver({1}),
            llm_client=StubLlmClient(),
        )
        registry = wiring_result.observation_registry
        trigger = wiring_result.llm_turn_trigger

        registry.register_handlers(event_publisher)

        event1 = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
        )
        event2 = PlayerLocationChangedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
            old_spot_id=SpotId(1),
            old_coordinate=Coordinate(0, 0, 0),
            new_spot_id=SpotId(2),
            new_coordinate=Coordinate(1, 0, 0),
        )

        with uow:
            uow.add_events([event1, event2])

        trigger.run_scheduled_turns()

        entries = episode_memory_store.get_recent(PlayerId(1), limit=10)
        assert len(entries) >= 1, "エピソード記憶に最低1件は保存されること（breaks_movement 観測）"

    def test_pursuit_failed_event_is_scheduled_by_observation_handler_and_drained_by_world_tick(
        self,
    ):
        from ai_rpg_world.application.llm.services.in_memory_episode_memory_store import (
            InMemoryEpisodeMemoryStore,
        )
        from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
        from ai_rpg_world.application.llm.services.llm_player_resolver import (
            SetBasedLlmPlayerResolver,
        )
        from ai_rpg_world.application.llm.services.sliding_window_memory import (
            DefaultSlidingWindowMemory,
        )
        from ai_rpg_world.application.world.services.world_query_service import (
            WorldQueryService,
        )
        from ai_rpg_world.application.world.services.world_simulation_service import (
            WorldSimulationApplicationService,
        )
        from ai_rpg_world.domain.common.value_object import WorldTick
        from ai_rpg_world.domain.combat.service.hit_box_collision_service import (
            HitBoxCollisionDomainService,
        )
        from ai_rpg_world.domain.combat.service.hit_box_config_service import (
            DefaultHitBoxConfigService,
        )
        from ai_rpg_world.domain.monster.aggregate.monster_aggregate import MonsterAggregate
        from ai_rpg_world.domain.monster.service.monster_skill_execution_domain_service import (
            MonsterSkillExecutionDomainService,
        )
        from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
            PlayerProfileAggregate,
        )
        from ai_rpg_world.domain.player.enum.player_enum import ControlType
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.domain.player.value_object.player_name import PlayerName
        from ai_rpg_world.domain.pursuit.enum.pursuit_failure_reason import (
            PursuitFailureReason,
        )
        from ai_rpg_world.domain.pursuit.event.pursuit_events import PursuitFailedEvent
        from ai_rpg_world.domain.pursuit.value_object.pursuit_last_known_state import (
            PursuitLastKnownState,
        )
        from ai_rpg_world.domain.pursuit.value_object.pursuit_target_snapshot import (
            PursuitTargetSnapshot,
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
        from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import (
            PhysicalMapAggregate,
        )
        from ai_rpg_world.domain.world.entity.tile import Tile
        from ai_rpg_world.domain.world.entity.world_object import WorldObject
        from ai_rpg_world.domain.world.entity.world_object_component import (
            ActorComponent,
        )
        from ai_rpg_world.domain.world.enum.world_enum import DirectionEnum, ObjectTypeEnum
        from ai_rpg_world.domain.world.service.behavior_service import BehaviorService
        from ai_rpg_world.domain.world.service.pathfinding_service import PathfindingService
        from ai_rpg_world.domain.world.service.weather_config_service import (
            DefaultWeatherConfigService,
        )
        from ai_rpg_world.domain.world.service.world_time_config_service import (
            DefaultWorldTimeConfigService,
        )
        from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.domain.world.value_object.world_object_id import WorldObjectId
        from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
        from ai_rpg_world.infrastructure.repository.in_memory_data_store import (
            InMemoryDataStore,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_hit_box_repository import (
            InMemoryHitBoxRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_monster_aggregate_repository import (
            InMemoryMonsterAggregateRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
            InMemoryPhysicalMapRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import (
            InMemoryPlayerProfileRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
            InMemoryPlayerStatusRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_spot_repository import (
            InMemorySpotRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_weather_zone_repository import (
            InMemoryWeatherZoneRepository,
        )
        from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
            InMemoryGameTimeProvider,
        )
        from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
            InMemoryUnitOfWork,
        )
        from ai_rpg_world.infrastructure.world.pathfinding.astar_pathfinding_strategy import (
            AStarPathfindingStrategy,
        )
        from ai_rpg_world.domain.world.entity.spot import Spot
        from ai_rpg_world.application.world.services.caching_pathfinding_service import (
            CachingPathfindingService,
        )
        from ai_rpg_world.domain.combat.service.hit_box_factory import HitBoxFactory
        from ai_rpg_world.domain.world.service.skill_selection_policy import (
            FirstInRangeSkillPolicy,
        )
        from ai_rpg_world.application.world.services.monster_action_resolver import (
            create_monster_action_resolver_factory,
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

        uow, event_publisher = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow,
            data_store=data_store,
        )

        profile_repo = InMemoryPlayerProfileRepository(data_store, None)
        profile_repo.save(
            PlayerProfileAggregate.create(
                PlayerId(1), PlayerName("Pursuer"), control_type=ControlType.LLM
            )
        )
        profile_repo.save(
            PlayerProfileAggregate.create(
                PlayerId(2), PlayerName("Runner"), control_type=ControlType.HUMAN
            )
        )
        spot_repo = InMemorySpotRepository(data_store, None)
        spot_repo.save(Spot(SpotId(1), "SpotA", "A"))

        player_status_repo = InMemoryPlayerStatusRepository(data_store, None)
        physical_map_repo = InMemoryPhysicalMapRepository(data_store, None)
        physical_map_repo.save(
            PhysicalMapAggregate.create(
                SpotId(1),
                [Tile(Coordinate(x, y, 0), TerrainType.grass()) for x in range(3) for y in range(3)],
                objects=[
                    WorldObject(
                        WorldObjectId(1),
                        Coordinate(0, 0, 0),
                        ObjectTypeEnum.PLAYER,
                        component=ActorComponent(
                            direction=DirectionEnum.EAST,
                            player_id=PlayerId(1),
                        ),
                    ),
                    WorldObject(
                        WorldObjectId(2),
                        Coordinate(1, 0, 0),
                        ObjectTypeEnum.PLAYER,
                        component=ActorComponent(
                            direction=DirectionEnum.WEST,
                            player_id=PlayerId(2),
                        ),
                    ),
                ],
            )
        )

        world_query = MagicMock(spec=WorldQueryService)
        world_query.get_player_current_state = MagicMock(return_value=None)
        movement = MagicMock(spec=MovementApplicationService)
        movement.move_to_destination = MagicMock()
        movement.cancel_movement = MagicMock()

        episode_memory_store = InMemoryEpisodeMemoryStore()
        sliding_window = DefaultSlidingWindowMemory(max_entries_per_player=1)
        uow_factory = MagicMock(spec=UnitOfWorkFactory)
        uow_factory.create.return_value = uow

        event = PursuitFailedEvent.create(
            aggregate_id=WorldObjectId(1),
            aggregate_type="PlayerStatusAggregate",
            actor_id=WorldObjectId(1),
            target_id=WorldObjectId(2),
            failure_reason=PursuitFailureReason.TARGET_MISSING,
            target_snapshot=PursuitTargetSnapshot(
                target_id=WorldObjectId(2),
                spot_id=SpotId(1),
                coordinate=Coordinate(1, 0, 0),
            ),
            last_known=PursuitLastKnownState(
                target_id=WorldObjectId(2),
                spot_id=SpotId(1),
                coordinate=Coordinate(1, 0, 0),
                observed_at_tick=WorldTick(10),
            ),
        )

        pathfinding_service = PathfindingService(AStarPathfindingStrategy())
        caching_pathfinding = CachingPathfindingService(
            pathfinding_service,
            time_provider=time_provider,
            ttl_ticks=5,
        )
        skill_execution_service = SkillExecutionDomainService(
            SkillTargetingDomainService(),
            SkillToHitBoxDomainService(),
        )
        pursuit_continuation_service = MagicMock()
        pursuit_command_service = MagicMock()

        def comp_builder(registry):
            return EventHandlerComposition(observation_registry=registry)

        def svc_builder(continuation_service, trigger, reflection_runner):
            return WorldSimulationApplicationService(
                time_provider=time_provider,
                physical_map_repository=physical_map_repo,
                weather_zone_repository=InMemoryWeatherZoneRepository(data_store, uow),
                player_status_repository=player_status_repo,
                hit_box_repository=InMemoryHitBoxRepository(data_store, uow),
                behavior_service=BehaviorService(),
                weather_config_service=DefaultWeatherConfigService(update_interval_ticks=1),
                unit_of_work=uow,
                monster_repository=InMemoryMonsterAggregateRepository(data_store, uow),
                skill_loadout_repository=_InMemorySkillLoadoutRepo(),
                monster_skill_execution_domain_service=MonsterSkillExecutionDomainService(
                    skill_execution_service
                ),
                hit_box_factory=HitBoxFactory(),
                hit_box_config_service=DefaultHitBoxConfigService(substeps_per_tick=4),
                hit_box_collision_service=HitBoxCollisionDomainService(),
                world_time_config_service=DefaultWorldTimeConfigService(ticks_per_day=24),
                monster_action_resolver_factory=create_monster_action_resolver_factory(
                    caching_pathfinding,
                    FirstInRangeSkillPolicy(),
                ),
                llm_turn_trigger=trigger,
                reflection_runner=reflection_runner,
                movement_service=movement,
                pursuit_continuation_service=continuation_service,
            )

        runtime = compose_player_pursuit_runtime(
            pursuit_command_service=pursuit_command_service,
            pursuit_continuation_service=pursuit_continuation_service,
            composition_builder=comp_builder,
            service_builder=svc_builder,
            player_status_repository=player_status_repo,
            physical_map_repository=physical_map_repo,
            world_query_service=world_query,
            movement_service=movement,
            player_profile_repository=profile_repo,
            unit_of_work_factory=uow_factory,
            spot_repository=spot_repo,
            episode_memory_store=episode_memory_store,
            sliding_window_memory=sliding_window,
            llm_player_resolver=SetBasedLlmPlayerResolver({1}),
            llm_client=StubLlmClient(),
            game_time_provider=time_provider,
            world_time_config_service=DefaultWorldTimeConfigService(ticks_per_day=24),
        )
        runtime.event_handler_composition.register_for_profile(
            event_publisher, EventHandlerProfile.FULL
        )
        trigger = runtime.llm_turn_trigger
        service = runtime.world_simulation_service
        assert service is not None
        assert service._pursuit_continuation_service is pursuit_continuation_service

        with patch.object(trigger, "schedule_turn", wraps=trigger.schedule_turn) as schedule_spy:
            with uow:
                uow.add_events([event])
            schedule_spy.assert_called_once_with(PlayerId(1))

        with patch.object(
            trigger, "run_scheduled_turns", wraps=trigger.run_scheduled_turns
        ) as run_spy:
            tick = service.tick()
            assert tick == WorldTick(11)
            run_spy.assert_called_once()

        entries = episode_memory_store.get_recent(PlayerId(1), limit=10)
        assert len(entries) >= 1


# ---------------------------------------------------------------------------
# E2E: domain event -> observation -> schedule_turn -> run_scheduled_turns -> tool execution -> world side effect
# ---------------------------------------------------------------------------


class TestEventToWorldSideEffectE2E:
    """domain event から world side effect（move_to_destination 呼び出し）までを含む E2E"""

    def test_domain_event_to_move_to_destination_invokes_movement_service(self):
        """
        domain event → 観測 → schedule_turn → run_scheduled_turns → move_to_destination ツール実行
        → movement_service.move_to_destination が呼ばれること。
        """
        from ai_rpg_world.application.llm.services.in_memory_episode_memory_store import (
            InMemoryEpisodeMemoryStore,
        )
        from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
        from ai_rpg_world.application.llm.services.llm_player_resolver import (
            SetBasedLlmPlayerResolver,
        )
        from ai_rpg_world.application.llm.services.sliding_window_memory import (
            DefaultSlidingWindowMemory,
        )
        from ai_rpg_world.application.world.contracts.dtos import (
            AvailableMoveDto,
            PlayerCurrentStateDto,
        )
        from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
        from ai_rpg_world.domain.player.event.status_events import (
            PlayerDownedEvent,
        )
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
            PlayerProfileAggregate,
        )
        from ai_rpg_world.domain.player.enum.player_enum import ControlType
        from ai_rpg_world.domain.player.value_object.player_name import PlayerName
        from ai_rpg_world.domain.world.entity.spot import Spot
        from ai_rpg_world.infrastructure.repository.in_memory_data_store import (
            InMemoryDataStore,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import (
            InMemoryPlayerProfileRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
            InMemoryPlayerStatusRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
            InMemoryPhysicalMapRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_spot_repository import (
            InMemorySpotRepository,
        )
        from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_MOVE_TO_DESTINATION

        data_store = InMemoryDataStore()
        data_store.clear_all()

        def create_uow():
            return InMemoryUnitOfWork(
                unit_of_work_factory=create_uow, data_store=data_store
            )

        uow, event_publisher = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow,
            data_store=data_store,
        )

        profile_repo = InMemoryPlayerProfileRepository(data_store, None)
        spot_repo = InMemorySpotRepository(data_store, None)
        profile = PlayerProfileAggregate.create(
            PlayerId(1), PlayerName("E2EPlayer"), control_type=ControlType.LLM
        )
        profile_repo.save(profile)
        spot_repo.save(Spot(SpotId(1), "SpotA", "A"))
        spot_repo.save(Spot(SpotId(2), "SpotB", "B"))

        player_status_repo = InMemoryPlayerStatusRepository(data_store, None)
        physical_map_repo = InMemoryPhysicalMapRepository(data_store, None)

        movement_service = MagicMock(spec=MovementApplicationService)
        movement_service.move_to_destination = MagicMock(
            return_value=MagicMock(success=True, message="moved")
        )
        movement_service.cancel_movement = MagicMock()

        available_moves = [
            AvailableMoveDto(
                spot_id=2,
                spot_name="SpotB",
                road_id=1,
                road_description="道",
                conditions_met=True,
                failed_conditions=[],
            )
        ]
        current_state = PlayerCurrentStateDto(
            player_id=1,
            player_name="E2EPlayer",
            current_spot_id=1,
            current_spot_name="SpotA",
            current_spot_description="A",
            x=0,
            y=0,
            z=0,
            area_id=1,
            area_name="Area1",
            current_player_count=0,
            current_player_ids=set(),
            connected_spot_ids={2},
            connected_spot_names={"SpotB"},
            weather_type="clear",
            weather_intensity=0.5,
            current_terrain_type="grass",
            visible_objects=[],
            view_distance=5,
            available_moves=available_moves,
            total_available_moves=1,
            attention_level=AttentionLevel.FULL,
            is_busy=False,
            inventory_items=[],
            chest_items=[],
            usable_skills=[],
            nearby_shops=[],
            available_trades=[],
            active_quests=[],
            guild_memberships=[],
            notable_objects=[],
            actionable_objects=[],
        )

        world_query = MagicMock(spec=WorldQueryService)
        world_query.get_player_current_state = MagicMock(return_value=current_state)

        episode_memory_store = InMemoryEpisodeMemoryStore()
        sliding_window = DefaultSlidingWindowMemory(max_entries_per_player=1)

        uow_factory = MagicMock(spec=UnitOfWorkFactory)
        uow_factory.create.return_value = uow

        stub_client = StubLlmClient(
            tool_call_to_return={
                "name": TOOL_NAME_MOVE_TO_DESTINATION,
                "arguments": json.dumps({"destination_label": "S1"}),
            }
        )

        wiring_result = create_llm_agent_wiring(
            player_status_repository=player_status_repo,
            physical_map_repository=physical_map_repo,
            world_query_service=world_query,
            movement_service=movement_service,
            player_profile_repository=profile_repo,
            unit_of_work_factory=uow_factory,
            spot_repository=spot_repo,
            episode_memory_store=episode_memory_store,
            sliding_window_memory=sliding_window,
            llm_player_resolver=SetBasedLlmPlayerResolver({1}),
            llm_client=stub_client,
        )
        registry = wiring_result.observation_registry
        trigger = wiring_result.llm_turn_trigger

        registry.register_handlers(event_publisher)

        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
        )

        with uow:
            uow.add_events([event])

        trigger.run_scheduled_turns()

        movement_service.move_to_destination.assert_called_once()
        call_kw = movement_service.move_to_destination.call_args[1]
        assert call_kw["player_id"] == 1
        assert call_kw["target_spot_id"] == 2
        assert call_kw["destination_type"] == "spot"

    def test_move_to_destination_with_l1_label_invokes_movement_service_with_location_params(
        self,
    ):
        """
        L1 ラベル指定で move_to_destination が destination_type=location, target_location_area_id
        付きで呼ばれること（スポット内ロケーション移動の E2E）。
        """
        from ai_rpg_world.application.llm.services.in_memory_episode_memory_store import (
            InMemoryEpisodeMemoryStore,
        )
        from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
        from ai_rpg_world.application.llm.services.llm_player_resolver import (
            SetBasedLlmPlayerResolver,
        )
        from ai_rpg_world.application.llm.services.sliding_window_memory import (
            DefaultSlidingWindowMemory,
        )
        from ai_rpg_world.application.world.contracts.dtos import (
            AvailableLocationAreaDto,
            PlayerCurrentStateDto,
        )
        from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
        from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
            PlayerProfileAggregate,
        )
        from ai_rpg_world.domain.player.enum.player_enum import ControlType
        from ai_rpg_world.domain.player.value_object.player_name import PlayerName
        from ai_rpg_world.domain.world.entity.spot import Spot
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.infrastructure.repository.in_memory_data_store import (
            InMemoryDataStore,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import (
            InMemoryPlayerProfileRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
            InMemoryPlayerStatusRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
            InMemoryPhysicalMapRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_spot_repository import (
            InMemorySpotRepository,
        )
        from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_MOVE_TO_DESTINATION

        data_store = InMemoryDataStore()
        data_store.clear_all()

        def create_uow():
            return InMemoryUnitOfWork(
                unit_of_work_factory=create_uow, data_store=data_store
            )

        uow, event_publisher = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow,
            data_store=data_store,
        )

        profile_repo = InMemoryPlayerProfileRepository(data_store, None)
        spot_repo = InMemorySpotRepository(data_store, None)
        profile = PlayerProfileAggregate.create(
            PlayerId(1), PlayerName("L1E2EPlayer"), control_type=ControlType.LLM
        )
        profile_repo.save(profile)
        spot_repo.save(Spot(SpotId(1), "SpotA", "A"))

        player_status_repo = InMemoryPlayerStatusRepository(data_store, None)
        physical_map_repo = InMemoryPhysicalMapRepository(data_store, None)

        movement_service = MagicMock(spec=MovementApplicationService)
        movement_service.move_to_destination = MagicMock(
            return_value=MagicMock(success=True, message="moved")
        )
        movement_service.cancel_movement = MagicMock()

        current_state = PlayerCurrentStateDto(
            player_id=1,
            player_name="L1E2EPlayer",
            current_spot_id=1,
            current_spot_name="SpotA",
            current_spot_description="A",
            x=0,
            y=0,
            z=0,
            area_id=1,
            area_name="Area1",
            current_player_count=0,
            current_player_ids=set(),
            connected_spot_ids=set(),
            connected_spot_names=set(),
            weather_type="clear",
            weather_intensity=0.5,
            current_terrain_type="grass",
            visible_objects=[],
            view_distance=5,
            available_moves=[],
            total_available_moves=0,
            attention_level=AttentionLevel.FULL,
            is_busy=False,
            inventory_items=[],
            chest_items=[],
            usable_skills=[],
            nearby_shops=[],
            available_trades=[],
            active_quests=[],
            guild_memberships=[],
            notable_objects=[],
            actionable_objects=[],
            available_location_areas=[AvailableLocationAreaDto(location_area_id=10, name="広場")],
        )

        world_query = MagicMock(spec=WorldQueryService)
        world_query.get_player_current_state = MagicMock(return_value=current_state)

        episode_memory_store = InMemoryEpisodeMemoryStore()
        sliding_window = DefaultSlidingWindowMemory(max_entries_per_player=1)

        uow_factory = MagicMock(spec=UnitOfWorkFactory)
        uow_factory.create.return_value = uow

        stub_client = StubLlmClient(
            tool_call_to_return={
                "name": TOOL_NAME_MOVE_TO_DESTINATION,
                "arguments": json.dumps({"destination_label": "L1"}),
            }
        )

        wiring_result = create_llm_agent_wiring(
            player_status_repository=player_status_repo,
            physical_map_repository=physical_map_repo,
            world_query_service=world_query,
            movement_service=movement_service,
            player_profile_repository=profile_repo,
            unit_of_work_factory=uow_factory,
            spot_repository=spot_repo,
            episode_memory_store=episode_memory_store,
            sliding_window_memory=sliding_window,
            llm_player_resolver=SetBasedLlmPlayerResolver({1}),
            llm_client=stub_client,
        )
        registry = wiring_result.observation_registry
        trigger = wiring_result.llm_turn_trigger

        registry.register_handlers(event_publisher)

        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
        )

        with uow:
            uow.add_events([event])

        trigger.run_scheduled_turns()

        movement_service.move_to_destination.assert_called_once()
        call_kw = movement_service.move_to_destination.call_args[1]
        assert call_kw["player_id"] == 1
        assert call_kw["destination_type"] == "location"
        assert call_kw["target_spot_id"] == 1
        assert call_kw["target_location_area_id"] == 10

    def test_move_to_destination_with_d1_label_invokes_movement_service_with_object_params(
        self,
    ):
        """
        D1 ラベル指定で move_to_destination が destination_type=object, target_world_object_id
        付きで呼ばれること（視界内オブジェクト移動の E2E）。
        """
        from ai_rpg_world.application.llm.services.in_memory_episode_memory_store import (
            InMemoryEpisodeMemoryStore,
        )
        from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
        from ai_rpg_world.application.llm.services.llm_player_resolver import (
            SetBasedLlmPlayerResolver,
        )
        from ai_rpg_world.application.llm.services.sliding_window_memory import (
            DefaultSlidingWindowMemory,
        )
        from ai_rpg_world.application.world.contracts.dtos import (
            PlayerCurrentStateDto,
            VisibleObjectDto,
        )
        from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
        from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
            PlayerProfileAggregate,
        )
        from ai_rpg_world.domain.player.enum.player_enum import ControlType
        from ai_rpg_world.domain.player.value_object.player_name import PlayerName
        from ai_rpg_world.domain.world.entity.spot import Spot
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.infrastructure.repository.in_memory_data_store import (
            InMemoryDataStore,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import (
            InMemoryPlayerProfileRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
            InMemoryPlayerStatusRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
            InMemoryPhysicalMapRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_spot_repository import (
            InMemorySpotRepository,
        )
        from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_MOVE_TO_DESTINATION

        data_store = InMemoryDataStore()
        data_store.clear_all()

        def create_uow():
            return InMemoryUnitOfWork(
                unit_of_work_factory=create_uow, data_store=data_store
            )

        uow, event_publisher = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow,
            data_store=data_store,
        )

        profile_repo = InMemoryPlayerProfileRepository(data_store, None)
        spot_repo = InMemorySpotRepository(data_store, None)
        profile = PlayerProfileAggregate.create(
            PlayerId(1), PlayerName("D1E2EPlayer"), control_type=ControlType.LLM
        )
        profile_repo.save(profile)
        spot_repo.save(Spot(SpotId(1), "SpotA", "A"))

        player_status_repo = InMemoryPlayerStatusRepository(data_store, None)
        physical_map_repo = InMemoryPhysicalMapRepository(data_store, None)

        movement_service = MagicMock(spec=MovementApplicationService)
        movement_service.move_to_destination = MagicMock(
            return_value=MagicMock(success=True, message="moved")
        )
        movement_service.cancel_movement = MagicMock()

        actionable_npc = VisibleObjectDto(
            object_id=200,
            object_type="NPC",
            x=2,
            y=0,
            z=0,
            distance=2,
            display_name="老人",
            object_kind="npc",
            available_interactions=["interact"],
        )
        current_state = PlayerCurrentStateDto(
            player_id=1,
            player_name="D1E2EPlayer",
            current_spot_id=1,
            current_spot_name="SpotA",
            current_spot_description="A",
            x=0,
            y=0,
            z=0,
            area_id=1,
            area_name="Area1",
            current_player_count=0,
            current_player_ids=set(),
            connected_spot_ids=set(),
            connected_spot_names=set(),
            weather_type="clear",
            weather_intensity=0.5,
            current_terrain_type="grass",
            visible_objects=[],
            view_distance=5,
            available_moves=[],
            total_available_moves=0,
            attention_level=AttentionLevel.FULL,
            is_busy=False,
            inventory_items=[],
            chest_items=[],
            usable_skills=[],
            nearby_shops=[],
            available_trades=[],
            active_quests=[],
            guild_memberships=[],
            notable_objects=[],
            actionable_objects=[actionable_npc],
        )

        world_query = MagicMock(spec=WorldQueryService)
        world_query.get_player_current_state = MagicMock(return_value=current_state)

        episode_memory_store = InMemoryEpisodeMemoryStore()
        sliding_window = DefaultSlidingWindowMemory(max_entries_per_player=1)

        uow_factory = MagicMock(spec=UnitOfWorkFactory)
        uow_factory.create.return_value = uow

        stub_client = StubLlmClient(
            tool_call_to_return={
                "name": TOOL_NAME_MOVE_TO_DESTINATION,
                "arguments": json.dumps({"destination_label": "D1"}),
            }
        )

        wiring_result = create_llm_agent_wiring(
            player_status_repository=player_status_repo,
            physical_map_repository=physical_map_repo,
            world_query_service=world_query,
            movement_service=movement_service,
            player_profile_repository=profile_repo,
            unit_of_work_factory=uow_factory,
            spot_repository=spot_repo,
            episode_memory_store=episode_memory_store,
            sliding_window_memory=sliding_window,
            llm_player_resolver=SetBasedLlmPlayerResolver({1}),
            llm_client=stub_client,
        )
        registry = wiring_result.observation_registry
        trigger = wiring_result.llm_turn_trigger

        registry.register_handlers(event_publisher)

        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
        )

        with uow:
            uow.add_events([event])

        trigger.run_scheduled_turns()

        movement_service.move_to_destination.assert_called_once()
        call_kw = movement_service.move_to_destination.call_args[1]
        assert call_kw["player_id"] == 1
        assert call_kw["destination_type"] == "object"
        assert call_kw["target_spot_id"] == 1
        assert call_kw["target_world_object_id"] == 200

    def test_pursuit_tool_invokes_pursuit_command_service(self):
        from ai_rpg_world.application.llm.services.in_memory_episode_memory_store import (
            InMemoryEpisodeMemoryStore,
        )
        from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
        from ai_rpg_world.application.llm.services.llm_player_resolver import (
            SetBasedLlmPlayerResolver,
        )
        from ai_rpg_world.application.llm.services.sliding_window_memory import (
            DefaultSlidingWindowMemory,
        )
        from ai_rpg_world.application.world.contracts.dtos import (
            PlayerCurrentStateDto,
            VisibleObjectDto,
        )
        from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
            PlayerProfileAggregate,
        )
        from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel, ControlType
        from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
        from ai_rpg_world.domain.player.value_object.player_name import PlayerName
        from ai_rpg_world.domain.world.entity.spot import Spot
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.infrastructure.repository.in_memory_data_store import (
            InMemoryDataStore,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
            InMemoryPhysicalMapRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_player_profile_repository import (
            InMemoryPlayerProfileRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
            InMemoryPlayerStatusRepository,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_spot_repository import (
            InMemorySpotRepository,
        )
        from ai_rpg_world.application.llm.tool_constants import TOOL_NAME_PURSUIT_START

        data_store = InMemoryDataStore()
        data_store.clear_all()

        def create_uow():
            return InMemoryUnitOfWork(
                unit_of_work_factory=create_uow, data_store=data_store
            )

        uow, event_publisher = InMemoryUnitOfWork.create_with_event_publisher(
            unit_of_work_factory=create_uow,
            data_store=data_store,
        )

        profile_repo = InMemoryPlayerProfileRepository(data_store, None)
        spot_repo = InMemorySpotRepository(data_store, None)
        profile = PlayerProfileAggregate.create(
            PlayerId(1), PlayerName("E2EPlayer"), control_type=ControlType.LLM
        )
        profile_repo.save(profile)
        spot_repo.save(Spot(SpotId(1), "SpotA", "A"))

        player_status_repo = InMemoryPlayerStatusRepository(data_store, None)
        physical_map_repo = InMemoryPhysicalMapRepository(data_store, None)

        movement_service = MagicMock(spec=MovementApplicationService)
        movement_service.move_to_destination = MagicMock()
        movement_service.cancel_movement = MagicMock()
        pursuit_service = MagicMock()
        pursuit_service.start_pursuit = MagicMock(
            return_value=MagicMock(success=True, message="追跡を開始しました。", no_op=False)
        )
        pursuit_service.cancel_pursuit = MagicMock()

        current_state = PlayerCurrentStateDto(
            player_id=1,
            player_name="E2EPlayer",
            current_spot_id=1,
            current_spot_name="SpotA",
            current_spot_description="A",
            x=0,
            y=0,
            z=0,
            area_id=1,
            area_name="Area1",
            current_player_count=1,
            current_player_ids={1, 2},
            connected_spot_ids=set(),
            connected_spot_names=set(),
            weather_type="clear",
            weather_intensity=0.5,
            current_terrain_type="grass",
            visible_objects=[
                VisibleObjectDto(
                    object_id=100,
                    object_type="player",
                    x=1,
                    y=0,
                    z=0,
                    distance=1,
                    display_name="Bob",
                    object_kind="player",
                    player_id_value=2,
                )
            ],
            view_distance=5,
            available_moves=[],
            total_available_moves=0,
            attention_level=AttentionLevel.FULL,
            is_busy=False,
            inventory_items=[],
            chest_items=[],
            usable_skills=[],
            nearby_shops=[],
            available_trades=[],
            active_quests=[],
            guild_memberships=[],
            notable_objects=[],
            actionable_objects=[],
        )
        world_query = MagicMock(spec=WorldQueryService)
        world_query.get_player_current_state = MagicMock(return_value=current_state)

        episode_memory_store = InMemoryEpisodeMemoryStore()
        sliding_window = DefaultSlidingWindowMemory(max_entries_per_player=1)

        uow_factory = MagicMock(spec=UnitOfWorkFactory)
        uow_factory.create.return_value = uow

        stub_client = StubLlmClient(
            tool_call_to_return={
                "name": TOOL_NAME_PURSUIT_START,
                "arguments": json.dumps({"target_label": "P1"}),
            }
        )

        pursuit_continuation_service = MagicMock()

        def comp_builder(registry):
            return EventHandlerComposition(observation_registry=registry)

        def svc_builder(continuation_service, trigger, reflection_runner):
            svc = MagicMock()
            svc._pursuit_continuation_service = continuation_service
            svc._llm_turn_trigger = trigger
            svc._reflection_runner = reflection_runner
            return svc

        runtime = compose_player_pursuit_runtime(
            pursuit_command_service=pursuit_service,
            pursuit_continuation_service=pursuit_continuation_service,
            composition_builder=comp_builder,
            service_builder=svc_builder,
            player_status_repository=player_status_repo,
            physical_map_repository=physical_map_repo,
            world_query_service=world_query,
            movement_service=movement_service,
            player_profile_repository=profile_repo,
            unit_of_work_factory=uow_factory,
            spot_repository=spot_repo,
            episode_memory_store=episode_memory_store,
            sliding_window_memory=sliding_window,
            llm_player_resolver=SetBasedLlmPlayerResolver({1}),
            llm_client=stub_client,
        )
        runtime.event_handler_composition.register_for_profile(
            event_publisher, EventHandlerProfile.FULL
        )
        trigger = runtime.llm_turn_trigger

        event = PlayerDownedEvent.create(
            aggregate_id=PlayerId(1),
            aggregate_type="PlayerStatusAggregate",
        )

        with uow:
            uow.add_events([event])

        trigger.run_scheduled_turns()

        pursuit_service.start_pursuit.assert_called_once()
        assert runtime.world_simulation_service._pursuit_continuation_service is pursuit_continuation_service
