"""1 ターン分のプロンプト組み立てのデフォルト実装"""

from datetime import datetime, timezone
from importlib import import_module
import logging
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

from ai_rpg_world.application.llm.contracts.dtos import (
    SystemPromptPlayerInfoDto,
)
from ai_rpg_world.application.llm.contracts.episodic_reinterpretation import (
    EpisodicRecallObservation,
    IEpisodicRecallBufferStore,
    IEpisodicReinterpretationJournalStore,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    IAvailableToolsProvider,
    IContextFormatStrategy,
    ICurrentStateFormatter,
    ILlmUiContextBuilder,
    IPromptBuilder,
    IRecentEventsFormatter,
    ISlidingWindowMemory,
    ISystemPromptBuilder,
)
from ai_rpg_world.application.llm.exceptions import PlayerProfileNotFoundForPromptException
from ai_rpg_world.application.llm.services.episodic_cue_rules import build_situation_episodic_cues
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    EpisodicPassiveRecallCandidate,
    EpisodicPassiveRecallRetrievalService,
)
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
DEFAULT_EPISODIC_PASSIVE_RECALL_LIMIT_PER_AXIS = 10
DEFAULT_EPISODIC_PASSIVE_RECALL_MAX_CANDIDATES = 10
MESSAGE_WHEN_PLAYER_NOT_PLACED = "現在地: 未配置。ゲームに参加するまで待機しています。"


def _join_passive_recall_texts(
    player_id: int,
    candidates: tuple[EpisodicPassiveRecallCandidate, ...],
    journal_store: IEpisodicReinterpretationJournalStore | None = None,
) -> str:
    """retrieve の候補順のまま、active 再解釈を優先して recall text を改行で連結する。"""
    parts: list[str] = []
    for cand in candidates:
        active = None
        if journal_store is not None:
            try:
                active = journal_store.get_active(player_id, cand.episode.episode_id)
            except Exception:
                active = None
        raw = active.current_recall_text if active is not None else cand.episode.recall_text
        text = raw.strip() if isinstance(raw, str) else ""
        if text:
            parts.append(text)
    return "\n".join(parts)


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
        persona_block_provider: Optional[Callable[[PlayerId], str]] = None,
        recent_observations_limit: int = DEFAULT_RECENT_OBSERVATIONS_LIMIT,
        recent_actions_limit: int = DEFAULT_RECENT_ACTIONS_LIMIT,
        default_action_instruction: str = DEFAULT_ACTION_INSTRUCTION,
        tile_map_view_distance: int = 5,
        episodic_passive_recall: Optional[EpisodicPassiveRecallRetrievalService] = None,
        episodic_passive_recall_limit_per_axis: int = DEFAULT_EPISODIC_PASSIVE_RECALL_LIMIT_PER_AXIS,
        episodic_passive_recall_max_candidates: int = DEFAULT_EPISODIC_PASSIVE_RECALL_MAX_CANDIDATES,
        episodic_recall_buffer_store: Optional[IEpisodicRecallBufferStore] = None,
        episodic_reinterpretation_journal_store: Optional[IEpisodicReinterpretationJournalStore] = None,
        episodic_turn_index_provider: Optional[Callable[[PlayerId], int]] = None,
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
        if persona_block_provider is not None and not callable(persona_block_provider):
            raise TypeError("persona_block_provider must be callable or None")
        if recent_observations_limit < 0:
            raise ValueError("recent_observations_limit must be 0 or greater")
        if recent_actions_limit < 0:
            raise ValueError("recent_actions_limit must be 0 or greater")
        if tile_map_view_distance < 0:
            raise ValueError("tile_map_view_distance must be 0 or greater")
        if not isinstance(default_action_instruction, str):
            raise TypeError("default_action_instruction must be str")
        if episodic_passive_recall is not None and not isinstance(
            episodic_passive_recall, EpisodicPassiveRecallRetrievalService
        ):
            raise TypeError(
                "episodic_passive_recall must be EpisodicPassiveRecallRetrievalService or None"
            )
        if episodic_passive_recall_limit_per_axis < 0:
            raise ValueError("episodic_passive_recall_limit_per_axis must be 0 or greater")
        if episodic_passive_recall_max_candidates < 0:
            raise ValueError("episodic_passive_recall_max_candidates must be 0 or greater")
        if episodic_recall_buffer_store is not None and not isinstance(
            episodic_recall_buffer_store, IEpisodicRecallBufferStore
        ):
            raise TypeError(
                "episodic_recall_buffer_store must be IEpisodicRecallBufferStore or None"
            )
        if episodic_reinterpretation_journal_store is not None and not isinstance(
            episodic_reinterpretation_journal_store,
            IEpisodicReinterpretationJournalStore,
        ):
            raise TypeError(
                "episodic_reinterpretation_journal_store must be "
                "IEpisodicReinterpretationJournalStore or None"
            )
        if episodic_turn_index_provider is not None and not callable(
            episodic_turn_index_provider
        ):
            raise TypeError("episodic_turn_index_provider must be callable or None")

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
        self._persona_block_provider = persona_block_provider
        self._recent_observations_limit = recent_observations_limit
        self._recent_actions_limit = recent_actions_limit
        self._default_action_instruction = default_action_instruction
        self._tile_map_view_distance = tile_map_view_distance
        self._episodic_passive_recall = episodic_passive_recall
        self._episodic_passive_recall_limit_per_axis = episodic_passive_recall_limit_per_axis
        self._episodic_passive_recall_max_candidates = episodic_passive_recall_max_candidates
        self._episodic_recall_buffer_store = episodic_recall_buffer_store
        self._episodic_reinterpretation_journal_store = episodic_reinterpretation_journal_store
        self._episodic_turn_index_provider = episodic_turn_index_provider
        self._logger = logging.getLogger(self.__class__.__name__)

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

        # 5. 利用可能ツール取得
        tools = self._available_tools_provider.get_available_tools(current_state_dto)

        # 6. 受動想起（任意注入）: runtime + 直近観測 structured から situation_cues → recall_text を連結
        relevant_memories_text = ""
        if self._episodic_passive_recall is not None:
            observation_structured = None
            if observations:
                observation_structured = observations[0].output.structured
            latest_action = action_results[0] if action_results else None
            situation_cues = build_situation_episodic_cues(
                runtime_context=ui_context.tool_runtime_context,
                observation_structured=observation_structured,
                latest_action=latest_action,
            )
            recall_result = self._episodic_passive_recall.retrieve(
                player_id=player_id.value,
                situation_cues=situation_cues,
                limit_per_axis=self._episodic_passive_recall_limit_per_axis,
                max_candidates=self._episodic_passive_recall_max_candidates,
            )
            relevant_memories_text = _join_passive_recall_texts(
                player_id.value,
                recall_result.candidates,
                self._episodic_reinterpretation_journal_store,
            )
            if self._episodic_recall_buffer_store is not None:
                turn_index = (
                    self._episodic_turn_index_provider(player_id)
                    if self._episodic_turn_index_provider is not None
                    else 0
                )
                situation_cue_keys = tuple(c.to_canonical() for c in situation_cues)
                for cand in recall_result.candidates:
                    try:
                        self._episodic_recall_buffer_store.append(
                            EpisodicRecallObservation(
                                recall_id=f"recall-{uuid4().hex}",
                                player_id=player_id.value,
                                episode_id=cand.episode.episode_id,
                                recalled_at=datetime.now(timezone.utc),
                                source_axes=cand.source_axes,
                                current_state_snapshot=current_state_text,
                                recent_events_snapshot=recent_events_text,
                                persona_snapshot=player_info.persona_block,
                                situation_cues=situation_cue_keys,
                                turn_index=turn_index,
                            )
                        )
                    except Exception as e:
                        self._logger.warning(
                            "Failed to record episodic recall observation; prompt build continues: %s",
                            e,
                            exc_info=True,
                        )

        context = self._context_format_strategy.format(
            current_state_text, recent_events_text, relevant_memories_text
        )

        # 6b. 直前ターン失敗時の補正（user 先頭に差し込み、次の 1 ツール向け）
        failure_block = build_pre_turn_failure_section(action_results[:2])

        body_parts: list[str] = []
        if failure_block:
            body_parts.append(failure_block)
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
        result["current_beliefs_snapshot"] = relevant_memories_text
        result["persona_snapshot"] = player_info.persona_block
        return result
