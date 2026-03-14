"""create_llm_agent_wiring のテスト（正常・境界・例外）"""

import pytest
from unittest.mock import MagicMock

from ai_rpg_world.application.llm.contracts.dtos import ToolRuntimeContextDto
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SKILL_ACCEPT_PROPOSAL,
    TOOL_NAME_SKILL_ACTIVATE_AWAKENED_MODE,
    TOOL_NAME_SKILL_EQUIP,
    TOOL_NAME_SKILL_REJECT_PROPOSAL,
)
from ai_rpg_world.application.llm.contracts.interfaces import ILlmTurnTrigger
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.wiring import create_llm_agent_wiring
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
    IObservationFormatter,
)
from ai_rpg_world.application.world.services.world_query_service import (
    WorldQueryService,
)
from ai_rpg_world.application.world.services.movement_service import (
    MovementApplicationService,
)
from ai_rpg_world.application.world.contracts.dtos import (
    AwakenedActionDto,
    EquipableSkillCandidateDto,
    PendingSkillProposalDto,
    PlayerCurrentStateDto,
    SkillEquipSlotDto,
    UsableSkillDto,
)
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.skill.enum.skill_enum import DeckTier, SkillProposalType
from ai_rpg_world.domain.common.unit_of_work_factory import UnitOfWorkFactory
from ai_rpg_world.domain.player.repository.player_profile_repository import (
    PlayerProfileRepository,
)
from ai_rpg_world.domain.player.repository.player_status_repository import (
    PlayerStatusRepository,
)
from ai_rpg_world.domain.world.repository.physical_map_repository import (
    PhysicalMapRepository,
)
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


def _skill_capable_service():
    service = MagicMock()
    service.use_skill = MagicMock()
    service.equip_skill = MagicMock()
    service.accept_skill_proposal = MagicMock()
    service.reject_skill_proposal = MagicMock()
    service.activate_awakened_mode = MagicMock()
    return service


def _skill_management_state() -> PlayerCurrentStateDto:
    return PlayerCurrentStateDto(
        player_id=1,
        player_name="P",
        current_spot_id=1,
        current_spot_name="A",
        current_spot_description="",
        x=0,
        y=0,
        z=0,
        area_id=None,
        area_name=None,
        current_player_count=0,
        current_player_ids=set(),
        connected_spot_ids=set(),
        connected_spot_names=set(),
        weather_type="clear",
        weather_intensity=0.0,
        current_terrain_type=None,
        visible_objects=[],
        view_distance=5,
        available_moves=[],
        total_available_moves=0,
        attention_level=AttentionLevel.FULL,
        usable_skills=[UsableSkillDto(10, 1, 1001, "火球")],
        equipable_skill_candidates=[
            EquipableSkillCandidateDto(10, 1001, "火球", DeckTier.NORMAL)
        ],
        skill_equip_slots=[
            SkillEquipSlotDto(10, DeckTier.NORMAL, 0, "通常スロット 1")
        ],
        pending_skill_proposals=[
            PendingSkillProposalDto(
                progress_id=20,
                proposal_id=2,
                offered_skill_id=3001,
                display_name="新しい攻撃手段",
                proposal_type=SkillProposalType.ADD,
                deck_tier=DeckTier.NORMAL,
                target_slot_index=0,
            )
        ],
        awakened_action=AwakenedActionDto(10, "覚醒モードを発動"),
    )


class TestCreateLlmAgentWiringReturnValues:
    """create_llm_agent_wiring の戻り値（正常）"""

    def test_returns_wiring_result_unpackable_to_registry_and_trigger(self):
        """返り値は unpacking で (registry, trigger) が取得でき、LlmAgentWiringResult を返す"""
        from ai_rpg_world.application.llm.wiring import LlmAgentWiringResult

        deps = _minimal_wiring_deps()
        result = create_llm_agent_wiring(**deps)
        assert isinstance(result, LlmAgentWiringResult)
        registry, trigger = result
        assert isinstance(registry, ObservationEventHandlerRegistry)
        assert isinstance(trigger, ILlmTurnTrigger)

    def test_registry_has_register_handlers(self):
        """返された Registry は register_handlers メソッドを持つ"""
        deps = _minimal_wiring_deps()
        registry, _ = create_llm_agent_wiring(**deps)
        assert hasattr(registry, "register_handlers")
        assert callable(registry.register_handlers)

    def test_trigger_has_schedule_turn_and_run_scheduled_turns(self):
        """返された Trigger は schedule_turn と run_scheduled_turns を持つ"""
        deps = _minimal_wiring_deps()
        _, trigger = create_llm_agent_wiring(**deps)
        assert hasattr(trigger, "schedule_turn")
        assert callable(trigger.schedule_turn)
        assert hasattr(trigger, "run_scheduled_turns")
        assert callable(trigger.run_scheduled_turns)

    def test_run_scheduled_turns_empty_does_not_raise(self):
        """スケジュール済みがいない状態で run_scheduled_turns を呼んでも例外が出ない"""
        deps = _minimal_wiring_deps()
        _, trigger = create_llm_agent_wiring(**deps)
        trigger.run_scheduled_turns()

    def test_accepts_optional_llm_client(self):
        """llm_client を渡した場合、そのクライアントが使われる（戻り値の型は同じ）"""
        deps = _minimal_wiring_deps()
        deps["llm_client"] = StubLlmClient()
        registry, trigger = create_llm_agent_wiring(**deps)
        assert isinstance(registry, ObservationEventHandlerRegistry)
        assert isinstance(trigger, ILlmTurnTrigger)

    def test_accepts_optional_observation_buffer(self):
        """observation_buffer を渡した場合、そのバッファが使われる"""
        custom_buffer = MagicMock(spec=IObservationContextBuffer)
        deps = _minimal_wiring_deps()
        deps["observation_buffer"] = custom_buffer
        registry, _ = create_llm_agent_wiring(**deps)
        assert registry._handler._appender._buffer is custom_buffer

    def test_accepts_optional_observation_formatter(self):
        """observation_formatter を渡した場合、そのフォーマッタがハンドラに渡される"""
        custom_formatter = MagicMock(spec=IObservationFormatter)
        deps = _minimal_wiring_deps()
        deps["observation_formatter"] = custom_formatter
        registry, _ = create_llm_agent_wiring(**deps)
        assert registry._handler._pipeline._formatter is custom_formatter

    def test_when_world_time_config_provided_reflection_runner_is_created(self):
        """world_time_config_service を渡した場合 reflection_runner が作成される"""
        from ai_rpg_world.domain.common.value_object import WorldTick
        from ai_rpg_world.domain.world.service.world_time_config_service import (
            DefaultWorldTimeConfigService,
        )

        deps = _minimal_wiring_deps()
        deps["world_time_config_service"] = DefaultWorldTimeConfigService(
            ticks_per_day=24
        )
        result = create_llm_agent_wiring(**deps)
        assert result.reflection_runner is not None
        assert hasattr(result.reflection_runner, "run_after_tick")
        assert callable(result.reflection_runner.run_after_tick)
        result.reflection_runner.run_after_tick(WorldTick(0))


class TestCreateLlmAgentWiringRequiredParams:
    """必須引数が None のときに TypeError を出す"""

    @pytest.fixture
    def deps(self):
        return _minimal_wiring_deps()

    def test_player_status_repository_none_raises_type_error(self, deps):
        """player_status_repository が None のとき TypeError"""
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


class TestCreateLlmAgentWiringEnvClient:
    """環境変数 LLM_CLIENT によるクライアント切り替え（llm_client 未指定時）"""

    def test_default_uses_stub_client_when_llm_client_not_passed(self, monkeypatch):
        """llm_client を渡さず LLM_CLIENT 未設定時は StubLlmClient が使われ run_scheduled_turns が動く"""
        monkeypatch.delenv("LLM_CLIENT", raising=False)
        deps = _minimal_wiring_deps()
        registry, trigger = create_llm_agent_wiring(**deps)
        trigger.run_scheduled_turns()

    def test_env_stub_uses_stub_client(self, monkeypatch):
        """LLM_CLIENT=stub のとき StubLlmClient が使われる"""
        monkeypatch.setenv("LLM_CLIENT", "stub")
        deps = _minimal_wiring_deps()
        registry, trigger = create_llm_agent_wiring(**deps)
        trigger.run_scheduled_turns()

    def test_env_litellm_uses_litellm_client(self, monkeypatch):
        """LLM_CLIENT=litellm のとき LiteLLMClient が使われ run_scheduled_turns が動作する（llm_client 未指定時）"""
        monkeypatch.setenv("LLM_CLIENT", "litellm")
        deps = _minimal_wiring_deps()
        registry, trigger = create_llm_agent_wiring(**deps)
        assert registry is not None
        assert trigger is not None
        trigger.run_scheduled_turns()

    def test_env_unknown_raises_value_error(self, monkeypatch):
        """LLM_CLIENT が stub / litellm 以外のとき ValueError が発生する"""
        monkeypatch.setenv("LLM_CLIENT", "openai")
        deps = _minimal_wiring_deps()
        with pytest.raises(ValueError, match="LLM_CLIENT must be one of"):
            create_llm_agent_wiring(**deps)

    def test_env_whitespace_only_raises_value_error(self, monkeypatch):
        """LLM_CLIENT が空白のみのとき strip 後に空となり ValueError が発生する"""
        monkeypatch.setenv("LLM_CLIENT", "   ")
        deps = _minimal_wiring_deps()
        with pytest.raises(ValueError, match="LLM_CLIENT must be one of"):
            create_llm_agent_wiring(**deps)

    def test_env_typo_raises_value_error(self, monkeypatch):
        """LLM_CLIENT の typo（litellm 以外の不明な値）で ValueError が発生する"""
        monkeypatch.setenv("LLM_CLIENT", "litelm")
        deps = _minimal_wiring_deps()
        with pytest.raises(ValueError, match="got: 'litelm'"):
            create_llm_agent_wiring(**deps)


class TestCreateLlmAgentWiringMemoryPersistence:
    """memory_db_path による記憶永続化の切り替え"""

    def test_memory_db_path_none_uses_in_memory_store(self):
        """memory_db_path 未指定時は InMemoryEpisodeMemoryStore が使われる"""
        from ai_rpg_world.application.llm.services.in_memory_episode_memory_store import (
            InMemoryEpisodeMemoryStore,
        )

        deps = _minimal_wiring_deps()
        result = create_llm_agent_wiring(**deps)
        trigger = result.llm_turn_trigger
        episode_store = trigger._turn_runner._orchestrator._episode_memory_store
        assert isinstance(episode_store, InMemoryEpisodeMemoryStore)

    def test_memory_db_path_provided_uses_sqlite_store(self, tmp_path):
        """memory_db_path 指定時は SqliteEpisodeMemoryStore が使われる"""
        from ai_rpg_world.infrastructure.llm.sqlite_episode_memory_store import (
            SqliteEpisodeMemoryStore,
        )

        db_path = tmp_path / "llm_memory.db"
        deps = _minimal_wiring_deps()
        deps["memory_db_path"] = str(db_path)
        result = create_llm_agent_wiring(**deps)
        trigger = result.llm_turn_trigger
        episode_store = trigger._turn_runner._orchestrator._episode_memory_store
        assert isinstance(episode_store, SqliteEpisodeMemoryStore)


class TestCreateLlmAgentWiringSkillTools:
    def test_skill_tool_service_enables_full_phase9_tool_family(self):
        deps = _minimal_wiring_deps()
        deps["skill_tool_service"] = _skill_capable_service()

        result = create_llm_agent_wiring(**deps)
        orchestrator = result.llm_turn_trigger._turn_runner._orchestrator
        provider = orchestrator._prompt_builder._available_tools_provider

        tools = provider.get_available_tools(_skill_management_state())
        names = [t["function"]["name"] for t in tools if t.get("type") == "function"]

        assert TOOL_NAME_SKILL_EQUIP in names
        assert TOOL_NAME_SKILL_ACCEPT_PROPOSAL in names
        assert TOOL_NAME_SKILL_REJECT_PROPOSAL in names
        assert TOOL_NAME_SKILL_ACTIVATE_AWAKENED_MODE in names

    def test_skill_tool_service_without_phase9_methods_raises_type_error(self):
        deps = _minimal_wiring_deps()
        class _IncompleteSkillToolService:
            def use_skill(self, **kwargs):
                return None
            def equip_skill(self, **kwargs):
                return None
            def accept_skill_proposal(self, **kwargs):
                return None
            def reject_skill_proposal(self, **kwargs):
                return None

        incomplete_service = _IncompleteSkillToolService()
        deps["skill_tool_service"] = incomplete_service

        with pytest.raises(TypeError, match="activate_awakened_mode"):
            create_llm_agent_wiring(**deps)

    def test_skill_tools_flow_from_ui_labels_to_mapper_execution(self):
        deps = _minimal_wiring_deps()
        skill_tool_service = _skill_capable_service()
        deps["skill_tool_service"] = skill_tool_service

        result = create_llm_agent_wiring(**deps)
        orchestrator = result.llm_turn_trigger._turn_runner._orchestrator
        prompt_builder = orchestrator._prompt_builder
        ui_context = prompt_builder._ui_context_builder.build(
            "state",
            _skill_management_state(),
        )
        assert isinstance(ui_context.tool_runtime_context, ToolRuntimeContextDto)

        equip_args = orchestrator._tool_argument_resolver.resolve(
            TOOL_NAME_SKILL_EQUIP,
            {"skill_label": "EK1", "slot_label": "ES1"},
            ui_context.tool_runtime_context,
        )
        accept_args = orchestrator._tool_argument_resolver.resolve(
            TOOL_NAME_SKILL_ACCEPT_PROPOSAL,
            {"proposal_label": "SP1"},
            ui_context.tool_runtime_context,
        )
        reject_args = orchestrator._tool_argument_resolver.resolve(
            TOOL_NAME_SKILL_REJECT_PROPOSAL,
            {"proposal_label": "SP1"},
            ui_context.tool_runtime_context,
        )
        awakened_args = orchestrator._tool_argument_resolver.resolve(
            TOOL_NAME_SKILL_ACTIVATE_AWAKENED_MODE,
            {"awakened_action_label": "AW1"},
            ui_context.tool_runtime_context,
        )

        equip_result = orchestrator._tool_command_mapper.execute(
            1,
            TOOL_NAME_SKILL_EQUIP,
            equip_args,
        )
        accept_result = orchestrator._tool_command_mapper.execute(
            1,
            TOOL_NAME_SKILL_ACCEPT_PROPOSAL,
            accept_args,
        )
        reject_result = orchestrator._tool_command_mapper.execute(
            1,
            TOOL_NAME_SKILL_REJECT_PROPOSAL,
            reject_args,
        )
        awakened_result = orchestrator._tool_command_mapper.execute(
            1,
            TOOL_NAME_SKILL_ACTIVATE_AWAKENED_MODE,
            awakened_args,
        )

        assert equip_result.success is True
        assert equip_result.message == "火球を通常スロット 1に装備しました。"
        assert accept_result.success is True
        assert accept_result.message == "新しい攻撃手段を受諾し、通常スロット 1に装備しました。"
        assert reject_result.success is True
        assert reject_result.message == "新しい攻撃手段を却下しました。"
        assert awakened_result.success is True
        assert awakened_result.message == "覚醒モードを発動しました。"
        skill_tool_service.equip_skill.assert_called_once_with(
            player_id=1,
            loadout_id=10,
            deck_tier=DeckTier.NORMAL,
            slot_index=0,
            skill_id=1001,
        )
        skill_tool_service.accept_skill_proposal.assert_called_once_with(
            progress_id=20,
            proposal_id=2,
        )
        skill_tool_service.reject_skill_proposal.assert_called_once_with(
            progress_id=20,
            proposal_id=2,
        )
        skill_tool_service.activate_awakened_mode.assert_called_once_with(
            player_id=1,
            loadout_id=10,
        )

    def test_memory_db_path_env_var_uses_sqlite_store_when_arg_not_passed(
        self, tmp_path, monkeypatch
    ):
        """memory_db_path 未指定かつ LLM_MEMORY_DB_PATH 環境変数が設定されているとき SqliteEpisodeMemoryStore が使われる"""
        from ai_rpg_world.infrastructure.llm.sqlite_episode_memory_store import (
            SqliteEpisodeMemoryStore,
        )

        db_path = tmp_path / "llm_memory_env.db"
        monkeypatch.setenv("LLM_MEMORY_DB_PATH", str(db_path))
        deps = _minimal_wiring_deps()
        result = create_llm_agent_wiring(**deps)
        trigger = result.llm_turn_trigger
        episode_store = trigger._turn_runner._orchestrator._episode_memory_store
        assert isinstance(episode_store, SqliteEpisodeMemoryStore)
