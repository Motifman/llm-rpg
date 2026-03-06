"""DefaultPromptBuilder のテスト（正常・例外）"""

import pytest

from ai_rpg_world.application.llm.services.prompt_builder import (
    DefaultPromptBuilder,
    MESSAGE_WHEN_PLAYER_NOT_PLACED,
)
from ai_rpg_world.application.llm.services.sliding_window_memory import (
    DefaultSlidingWindowMemory,
)
from ai_rpg_world.application.llm.services.action_result_store import (
    DefaultActionResultStore,
)
from ai_rpg_world.application.llm.services.current_state_formatter import (
    DefaultCurrentStateFormatter,
)
from ai_rpg_world.application.llm.services.recent_events_formatter import (
    DefaultRecentEventsFormatter,
)
from ai_rpg_world.application.llm.services.available_tools_provider import (
    DefaultAvailableToolsProvider,
)
from ai_rpg_world.application.llm.services.context_format_strategy import (
    SectionBasedContextFormatStrategy,
)
from ai_rpg_world.application.llm.services.game_tool_registry import (
    DefaultGameToolRegistry,
)
from ai_rpg_world.application.llm.services.in_memory_episode_memory_store import (
    InMemoryEpisodeMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_long_term_memory_store import (
    InMemoryLongTermMemoryStore,
)
from ai_rpg_world.application.llm.services.predictive_memory_retriever import (
    DefaultPredictiveMemoryRetriever,
)
from ai_rpg_world.application.llm.services.system_prompt_builder import (
    DefaultSystemPromptBuilder,
)
from ai_rpg_world.application.llm.services.tool_definitions import (
    register_default_tools,
)
from ai_rpg_world.application.llm.exceptions import PlayerProfileNotFoundForPromptException
from ai_rpg_world.application.observation.services.observation_context_buffer import (
    DefaultObservationContextBuffer,
)
from ai_rpg_world.application.world.services.world_query_service import WorldQueryService
from ai_rpg_world.application.world.contracts.queries import GetPlayerCurrentStateQuery
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_name import PlayerName
from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import (
    PlayerProfileAggregate,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
from ai_rpg_world.domain.player.enum.player_enum import Role
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
from ai_rpg_world.domain.world.entity.spot import Spot
from ai_rpg_world.domain.world.aggregate.physical_map_aggregate import (
    PhysicalMapAggregate,
)
from ai_rpg_world.domain.world.entity.tile import Tile
from ai_rpg_world.domain.world.value_object.terrain_type import TerrainType
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
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
from ai_rpg_world.application.world.services.gateway_based_connected_spots_provider import (
    GatewayBasedConnectedSpotsProvider,
)


class TestDefaultPromptBuilder:
    """DefaultPromptBuilder の正常・例外ケース"""

    @pytest.fixture
    def setup_prompt_builder(self):
        """WorldQueryService と PromptBuilder を組み立てる。プロフィールのみ登録（未配置）。"""
        data_store = InMemoryDataStore()
        data_store.clear_all()
        profile_repo = InMemoryPlayerProfileRepository(data_store)
        status_repo = InMemoryPlayerStatusRepository(data_store)
        phys_repo = InMemoryPhysicalMapRepository(data_store)
        spot_repo = InMemorySpotRepository(data_store)
        spot_repo.save(Spot(SpotId(1), "Default", ""))
        connected = GatewayBasedConnectedSpotsProvider(phys_repo)
        world_query = WorldQueryService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
            connected_spots_provider=connected,
        )
        buffer = DefaultObservationContextBuffer()
        sliding = DefaultSlidingWindowMemory()
        action_store = DefaultActionResultStore()
        formatter = DefaultCurrentStateFormatter()
        recent_formatter = DefaultRecentEventsFormatter()
        strategy = SectionBasedContextFormatStrategy()
        system_builder = DefaultSystemPromptBuilder()
        registry = DefaultGameToolRegistry()
        register_default_tools(registry)
        tools_provider = DefaultAvailableToolsProvider(registry)
        prompt_builder = DefaultPromptBuilder(
            observation_buffer=buffer,
            sliding_window_memory=sliding,
            action_result_store=action_store,
            world_query_service=world_query,
            player_profile_repository=profile_repo,
            current_state_formatter=formatter,
            recent_events_formatter=recent_formatter,
            context_format_strategy=strategy,
            system_prompt_builder=system_builder,
            available_tools_provider=tools_provider,
        )
        return prompt_builder, profile_repo, status_repo, phys_repo, spot_repo, buffer

    def _create_profile(self, player_id: int, name: str = "TestPlayer"):
        return PlayerProfileAggregate.create(
            player_id=PlayerId(player_id),
            name=PlayerName(name),
            role=Role.CITIZEN,
        )

    def test_build_returns_messages_and_tools_structure(
        self, setup_prompt_builder
    ):
        """build が messages / tools / tool_choice を持つ辞書を返す"""
        prompt_builder, profile_repo, *_ = setup_prompt_builder
        profile_repo.save(self._create_profile(1, "Alice"))
        result = prompt_builder.build(PlayerId(1))
        assert "messages" in result
        assert "tools" in result
        assert result["tool_choice"] == "required"
        assert "overflow" in result
        assert len(result["messages"]) == 2
        assert result["messages"][0]["role"] == "system"
        assert result["messages"][1]["role"] == "user"
        assert "Alice" in result["messages"][0]["content"]
        assert "現在地: 未配置" in result["messages"][1]["content"]
        assert MESSAGE_WHEN_PLAYER_NOT_PLACED in result["messages"][1]["content"]
        # 未配置でも no_op は常に利用可能なので tools は空でない
        assert isinstance(result["tools"], list)
        assert len(result["tools"]) >= 1
        tool_names = [t["function"]["name"] for t in result["tools"] if t.get("type") == "function"]
        assert "world_no_op" in tool_names

    def test_build_with_predictive_retriever_includes_related_memories_section(
        self, setup_prompt_builder
    ):
        """predictive_memory_retriever を渡すと user に「関連する記憶」が含まれる"""
        prompt_builder, profile_repo, *_ = setup_prompt_builder
        profile_repo.save(self._create_profile(1, "Alice"))
        episode_store = InMemoryEpisodeMemoryStore()
        long_term_store = InMemoryLongTermMemoryStore()
        long_term_store.add_fact(PlayerId(1), "洞窟の奥には宝箱がある")
        retriever = DefaultPredictiveMemoryRetriever(
            episode_store=episode_store,
            long_term_store=long_term_store,
        )
        pb_with_memory = DefaultPromptBuilder(
            observation_buffer=setup_prompt_builder[0]._observation_buffer,
            sliding_window_memory=setup_prompt_builder[0]._sliding_window,
            action_result_store=setup_prompt_builder[0]._action_result_store,
            world_query_service=setup_prompt_builder[0]._world_query_service,
            player_profile_repository=profile_repo,
            current_state_formatter=setup_prompt_builder[0]._current_state_formatter,
            recent_events_formatter=setup_prompt_builder[0]._recent_events_formatter,
            context_format_strategy=setup_prompt_builder[0]._context_format_strategy,
            system_prompt_builder=setup_prompt_builder[0]._system_prompt_builder,
            available_tools_provider=setup_prompt_builder[0]._available_tools_provider,
            predictive_memory_retriever=retriever,
        )
        result = pb_with_memory.build(PlayerId(1))
        user_content = result["messages"][1]["content"]
        assert "関連する記憶" in user_content
        assert "宝箱" in user_content

    def test_build_raises_when_profile_not_found(self, setup_prompt_builder):
        """プロフィールが存在しないとき PlayerProfileNotFoundForPromptException"""
        prompt_builder, *_ = setup_prompt_builder
        with pytest.raises(PlayerProfileNotFoundForPromptException) as exc_info:
            prompt_builder.build(PlayerId(999))
        assert exc_info.value.player_id == 999

    def test_build_player_id_not_player_id_raises_type_error(
        self, setup_prompt_builder
    ):
        """player_id が PlayerId でないとき TypeError"""
        prompt_builder, profile_repo, *_ = setup_prompt_builder
        profile_repo.save(self._create_profile(1))
        with pytest.raises(TypeError, match="player_id must be PlayerId"):
            prompt_builder.build(1)  # type: ignore[arg-type]

    def test_build_action_instruction_not_str_raises_type_error(
        self, setup_prompt_builder
    ):
        """action_instruction が str でないとき（None 以外）TypeError"""
        prompt_builder, profile_repo, *_ = setup_prompt_builder
        profile_repo.save(self._create_profile(1))
        with pytest.raises(TypeError, match="action_instruction must be str or None"):
            prompt_builder.build(PlayerId(1), action_instruction=123)  # type: ignore[arg-type]

    def test_build_action_instruction_none_uses_default(self, setup_prompt_builder):
        """action_instruction が None のときデフォルト文言が user に含まれる"""
        prompt_builder, profile_repo, *_ = setup_prompt_builder
        profile_repo.save(self._create_profile(1))
        result = prompt_builder.build(PlayerId(1))
        assert "利用可能なツールで次の行動を選んでください。" in result["messages"][1]["content"]

    def test_build_custom_action_instruction_appears_in_user_content(
        self, setup_prompt_builder
    ):
        """action_instruction を渡すと user の末尾に含まれる"""
        prompt_builder, profile_repo, *_ = setup_prompt_builder
        profile_repo.save(self._create_profile(1))
        result = prompt_builder.build(
            PlayerId(1),
            action_instruction="次のアクションを選んでください。",
        )
        assert "次のアクションを選んでください。" in result["messages"][1]["content"]

    def test_init_available_tools_provider_not_provider_raises_type_error(
        self, setup_prompt_builder
    ):
        """コンストラクタで available_tools_provider が IAvailableToolsProvider でないとき TypeError"""
        _, profile_repo, status_repo, phys_repo, spot_repo, buffer = setup_prompt_builder
        sliding = DefaultSlidingWindowMemory()
        action_store = DefaultActionResultStore()
        formatter = DefaultCurrentStateFormatter()
        recent_formatter = DefaultRecentEventsFormatter()
        strategy = SectionBasedContextFormatStrategy()
        system_builder = DefaultSystemPromptBuilder()
        registry = DefaultGameToolRegistry()
        register_default_tools(registry)
        connected = GatewayBasedConnectedSpotsProvider(phys_repo)
        world_query = WorldQueryService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
            connected_spots_provider=connected,
        )
        with pytest.raises(TypeError, match="available_tools_provider must be IAvailableToolsProvider"):
            DefaultPromptBuilder(
                observation_buffer=buffer,
                sliding_window_memory=sliding,
                action_result_store=action_store,
                world_query_service=world_query,
                player_profile_repository=profile_repo,
                current_state_formatter=formatter,
                recent_events_formatter=recent_formatter,
                context_format_strategy=strategy,
                system_prompt_builder=system_builder,
                available_tools_provider=None,  # type: ignore[arg-type]
            )

    def test_init_default_action_instruction_not_str_raises_type_error(
        self, setup_prompt_builder
    ):
        """コンストラクタで default_action_instruction が str でないとき TypeError"""
        _, profile_repo, status_repo, phys_repo, spot_repo, buffer = setup_prompt_builder
        sliding = DefaultSlidingWindowMemory()
        action_store = DefaultActionResultStore()
        formatter = DefaultCurrentStateFormatter()
        recent_formatter = DefaultRecentEventsFormatter()
        strategy = SectionBasedContextFormatStrategy()
        system_builder = DefaultSystemPromptBuilder()
        registry = DefaultGameToolRegistry()
        register_default_tools(registry)
        tools_provider = DefaultAvailableToolsProvider(registry)
        connected = GatewayBasedConnectedSpotsProvider(phys_repo)
        world_query = WorldQueryService(
            player_status_repository=status_repo,
            player_profile_repository=profile_repo,
            physical_map_repository=phys_repo,
            spot_repository=spot_repo,
            connected_spots_provider=connected,
        )
        with pytest.raises(TypeError, match="default_action_instruction must be str"):
            DefaultPromptBuilder(
                observation_buffer=buffer,
                sliding_window_memory=sliding,
                action_result_store=action_store,
                world_query_service=world_query,
                player_profile_repository=profile_repo,
                current_state_formatter=formatter,
                recent_events_formatter=recent_formatter,
                context_format_strategy=strategy,
                system_prompt_builder=system_builder,
                available_tools_provider=tools_provider,
                default_action_instruction=123,  # type: ignore[arg-type]
            )
