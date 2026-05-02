"""1 ターン分のプロンプト組み立てのデフォルト実装"""

from importlib import import_module
from typing import Any, Callable, Dict, List, Optional

from ai_rpg_world.application.llm.contracts.dtos import (
    EpisodeEncodingContextDto,
    SystemPromptPlayerInfoDto,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    IAvailableToolsProvider,
    IContextFormatStrategy,
    ICurrentStateFormatter,
    ILlmUiContextBuilder,
    IPassiveSubjectiveRecallComposer,
    IPredictiveMemoryRetriever,
    IPromptBuilder,
    IRecentEventsFormatter,
    ISlidingWindowMemory,
    ISystemPromptBuilder,
)
from ai_rpg_world.application.llm.exceptions import PlayerProfileNotFoundForPromptException
from ai_rpg_world.application.llm.services.failure_feedback_for_prompt import (
    build_pre_turn_failure_section,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
)
from ai_rpg_world.application.world.contracts.queries import GetPlayerCurrentStateQuery
from ai_rpg_world.application.world.services.world_query_service import WorldQueryService
from ai_rpg_world.domain.player.repository.player_profile_repository import (
    PlayerProfileRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


DEFAULT_ACTION_INSTRUCTION = "利用可能なツールで次の行動を選んでください。"
DEFAULT_RECENT_OBSERVATIONS_LIMIT = 20
DEFAULT_RECENT_ACTIONS_LIMIT = 20
MESSAGE_WHEN_PLAYER_NOT_PLACED = "現在地: 未配置。ゲームに参加するまで待機しています。"


class DefaultPromptBuilder(IPromptBuilder):
    """
    観測バッファの drain → スライディングウィンドウへの append と、
    現在状態・直近の出来事・システムプロンプトの組み立てを行う。
    """

    def __init__(
        self,
        observation_buffer: IObservationContextBuffer,
        sliding_window_memory: ISlidingWindowMemory,
        action_result_store: IActionResultStore,
        world_query_service: WorldQueryService,
        player_profile_repository: PlayerProfileRepository,
        current_state_formatter: ICurrentStateFormatter,
        recent_events_formatter: IRecentEventsFormatter,
        context_format_strategy: IContextFormatStrategy,
        system_prompt_builder: ISystemPromptBuilder,
        available_tools_provider: IAvailableToolsProvider,
        ui_context_builder: Optional[ILlmUiContextBuilder] = None,
        predictive_memory_retriever: Optional[IPredictiveMemoryRetriever] = None,
        persona_block_provider: Optional[Callable[[PlayerId], str]] = None,
        passive_subjective_recall: Optional[IPassiveSubjectiveRecallComposer] = None,
        episode_encoding_context_provider: Optional[
            Callable[[PlayerId], EpisodeEncodingContextDto]
        ] = None,
        recent_observations_limit: int = DEFAULT_RECENT_OBSERVATIONS_LIMIT,
        recent_actions_limit: int = DEFAULT_RECENT_ACTIONS_LIMIT,
        default_action_instruction: str = DEFAULT_ACTION_INSTRUCTION,
        tile_map_view_distance: int = 5,
    ) -> None:
        if not isinstance(observation_buffer, IObservationContextBuffer):
            raise TypeError("observation_buffer must be IObservationContextBuffer")
        if not isinstance(sliding_window_memory, ISlidingWindowMemory):
            raise TypeError("sliding_window_memory must be ISlidingWindowMemory")
        if not isinstance(action_result_store, IActionResultStore):
            raise TypeError("action_result_store must be IActionResultStore")
        if not isinstance(world_query_service, WorldQueryService):
            raise TypeError("world_query_service must be WorldQueryService")
        if not isinstance(player_profile_repository, PlayerProfileRepository):
            raise TypeError("player_profile_repository must be PlayerProfileRepository")
        if not isinstance(current_state_formatter, ICurrentStateFormatter):
            raise TypeError("current_state_formatter must be ICurrentStateFormatter")
        if not isinstance(recent_events_formatter, IRecentEventsFormatter):
            raise TypeError("recent_events_formatter must be IRecentEventsFormatter")
        if not isinstance(context_format_strategy, IContextFormatStrategy):
            raise TypeError("context_format_strategy must be IContextFormatStrategy")
        if not isinstance(system_prompt_builder, ISystemPromptBuilder):
            raise TypeError("system_prompt_builder must be ISystemPromptBuilder")
        if not isinstance(available_tools_provider, IAvailableToolsProvider):
            raise TypeError("available_tools_provider must be IAvailableToolsProvider")
        if ui_context_builder is not None and not isinstance(
            ui_context_builder, ILlmUiContextBuilder
        ):
            raise TypeError("ui_context_builder must be ILlmUiContextBuilder or None")
        if predictive_memory_retriever is not None and not isinstance(
            predictive_memory_retriever, IPredictiveMemoryRetriever
        ):
            raise TypeError(
                "predictive_memory_retriever must be IPredictiveMemoryRetriever or None"
            )
        if persona_block_provider is not None and not callable(persona_block_provider):
            raise TypeError("persona_block_provider must be callable or None")
        if passive_subjective_recall is not None and not isinstance(
            passive_subjective_recall, IPassiveSubjectiveRecallComposer
        ):
            raise TypeError(
                "passive_subjective_recall must be IPassiveSubjectiveRecallComposer or None"
            )
        if episode_encoding_context_provider is not None and not callable(
            episode_encoding_context_provider
        ):
            raise TypeError(
                "episode_encoding_context_provider must be callable or None"
            )
        if recent_observations_limit < 0:
            raise ValueError("recent_observations_limit must be 0 or greater")
        if recent_actions_limit < 0:
            raise ValueError("recent_actions_limit must be 0 or greater")
        if tile_map_view_distance < 0:
            raise ValueError("tile_map_view_distance must be 0 or greater")
        if not isinstance(default_action_instruction, str):
            raise TypeError("default_action_instruction must be str")

        self._observation_buffer = observation_buffer
        self._sliding_window = sliding_window_memory
        self._action_result_store = action_result_store
        self._world_query_service = world_query_service
        self._profile_repository = player_profile_repository
        self._current_state_formatter = current_state_formatter
        self._recent_events_formatter = recent_events_formatter
        self._context_format_strategy = context_format_strategy
        self._system_prompt_builder = system_prompt_builder
        self._available_tools_provider = available_tools_provider
        if ui_context_builder is not None:
            self._ui_context_builder = ui_context_builder
        else:
            builder_module = import_module(
                "ai_rpg_world.application.llm.services.ui_context_builder"
            )
            self._ui_context_builder = builder_module.DefaultLlmUiContextBuilder()
        self._predictive_memory_retriever = predictive_memory_retriever
        self._persona_block_provider = persona_block_provider
        self._passive_subjective_recall = passive_subjective_recall
        self._episode_encoding_context_provider = episode_encoding_context_provider
        self._recent_observations_limit = recent_observations_limit
        self._recent_actions_limit = recent_actions_limit
        self._default_action_instruction = default_action_instruction
        self._tile_map_view_distance = tile_map_view_distance

    def build(
        self,
        player_id: PlayerId,
        action_instruction: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if action_instruction is not None and not isinstance(action_instruction, str):
            raise TypeError("action_instruction must be str or None")

        # 1. プロフィール取得（システムプロンプト用。必須）
        profile = self._profile_repository.find_by_id(player_id)
        if profile is None:
            raise PlayerProfileNotFoundForPromptException(player_id.value)
        player_info = SystemPromptPlayerInfoDto(
            player_name=profile.name.value,
            role=profile.role.value,
            race=profile.race.value,
            element=profile.element.value,
            game_description="",
            persona_block=(
                self._persona_block_provider(player_id)
                if self._persona_block_provider is not None
                else ""
            ),
        )

        # 2. drain してスライディングウィンドウに append（溢れは記憶抽出用に返す）
        drained = self._observation_buffer.drain(player_id)
        overflow: List[ObservationEntry] = []
        if drained:
            overflow = self._sliding_window.append_all(player_id, drained)

        # 3. 現在状態取得（None の場合はプレースホルダ）
        current_state_dto = self._world_query_service.get_player_current_state(
            GetPlayerCurrentStateQuery(
                player_id=player_id.value,
                view_distance=self._tile_map_view_distance,
            )
        )
        if current_state_dto is not None:
            base_current_state_text = self._current_state_formatter.format(current_state_dto)
        else:
            base_current_state_text = MESSAGE_WHEN_PLAYER_NOT_PLACED
        ui_context = self._ui_context_builder.build(
            base_current_state_text,
            current_state_dto,
        )
        current_state_text = ui_context.current_state_text

        # 4. 直近の出来事（観測＋行動結果をマージ）
        observations = self._sliding_window.get_recent(
            player_id, self._recent_observations_limit
        )
        action_results = self._action_result_store.get_recent(
            player_id, self._recent_actions_limit
        )
        recent_events_text = self._recent_events_formatter.format(
            observations, action_results
        )

        # 5. 利用可能ツール取得（関連記憶の候補行動名と返り値の両方で使用）
        tools = self._available_tools_provider.get_available_tools(current_state_dto)
        tool_names = [
            t["function"]["name"]
            for t in tools
            if t.get("type") == "function" and "function" in t
        ]

        # 6. 関連する記憶（Retriever が設定されていれば取得）
        if self._predictive_memory_retriever is not None:
            from ai_rpg_world.application.llm.services.predictive_memory_retriever import (
                build_memory_retrieval_query_from_state,
            )

            query_dto = None
            if current_state_dto is not None:
                query_dto = build_memory_retrieval_query_from_state(
                    current_state_dto,
                    tool_names,
                    current_state_summary=base_current_state_text,
                )
            relevant_memories_text = (
                self._predictive_memory_retriever.retrieve_for_prediction(
                    player_id,
                    base_current_state_text,
                    tool_names,
                    query_dto=query_dto,
                )
            )
        else:
            relevant_memories_text = ""
        context = self._context_format_strategy.format(
            current_state_text, recent_events_text, relevant_memories_text
        )

        # 6b. 直前ターン失敗時の補正（user 先頭に差し込み、次の 1 ツール向け）
        failure_block = build_pre_turn_failure_section(action_results[:2])
        recall_block = ""
        goals_snapshot = ""
        identity_snapshot = ""
        if self._episode_encoding_context_provider is not None:
            enc_ctx = self._episode_encoding_context_provider(player_id)
            if not isinstance(enc_ctx, EpisodeEncodingContextDto):
                raise TypeError(
                    "episode_encoding_context_provider must return EpisodeEncodingContextDto"
                )
            goals_snapshot = enc_ctx.current_goals or ""
            identity_snapshot = enc_ctx.identity_summary or ""
        if self._passive_subjective_recall is not None:
            situation_for_recall = (
                current_state_text.rstrip() + "\n" + recent_events_text.rstrip()
            ).strip()
            recall = self._passive_subjective_recall.compose_user_block(
                player_id,
                situation_text=situation_for_recall,
                current_goals_hint=goals_snapshot,
                runtime_context=ui_context.tool_runtime_context,
            )
            recall_block = recall.user_block.strip()
            passive_recall_episode_ids = recall.episode_ids_for_reflection
            passive_recall_situation_text = situation_for_recall
        else:
            passive_recall_episode_ids = ()
            passive_recall_situation_text = ""

        body_parts: list[str] = []
        if failure_block:
            body_parts.append(failure_block)
        if recall_block:
            body_parts.append(recall_block)
        body_parts.append(context.rstrip())
        user_context_body = "\n\n".join(body_parts)

        # 7. システムプロンプト・ユーザーメッセージ
        system_content = self._system_prompt_builder.build(player_info)
        instruction = action_instruction or self._default_action_instruction
        user_content = user_context_body + "\n\n" + instruction

        result: Dict[str, Any] = {
            "messages": [
                {"role": "system", "content": system_content},
                {"role": "user", "content": user_content},
            ],
            "tools": tools,
            "tool_choice": "required",
        }
        result["overflow"] = overflow
        result["tool_runtime_context"] = ui_context.tool_runtime_context
        result["current_state_snapshot"] = current_state_text
        result["current_goals_snapshot"] = goals_snapshot
        result["current_beliefs_snapshot"] = relevant_memories_text
        result["identity_snapshot"] = identity_snapshot
        result["persona_snapshot"] = player_info.persona_block
        result["working_memory_snapshot"] = ()
        result["passive_recall_reflection_episode_ids"] = passive_recall_episode_ids
        result["passive_recall_situation_text"] = passive_recall_situation_text
        return result
