"""1 ターン分のプロンプト組み立てのデフォルト実装"""

import logging
from datetime import datetime, timezone
from importlib import import_module
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
    IMemoStore,
    IPromptBuilder,
    IRecentEventsFormatter,
    ISlidingWindowMemory,
    ISystemPromptBuilder,
)
from ai_rpg_world.application.llm.exceptions import PlayerProfileNotFoundForPromptException
from ai_rpg_world.application.llm.services.active_memos_formatter import (
    format_active_memos,
)
from ai_rpg_world.application.llm.services.episodic_cue_rules import build_situation_episodic_cues
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    EpisodicPassiveRecallCandidate,
    EpisodicPassiveRecallRetrievalService,
)
from ai_rpg_world.application.llm.services.episodic_memory_link_application_service import (
    EpisodicMemoryLinkApplicationService,
)
from ai_rpg_world.application.llm.services.prompt_builder_config import (
    DEFAULT_ACTION_INSTRUCTION as _CFG_DEFAULT_ACTION_INSTRUCTION,
    DEFAULT_EPISODIC_PASSIVE_RECALL_LIMIT_PER_AXIS as _CFG_DEFAULT_EPISODIC_PASSIVE_RECALL_LIMIT_PER_AXIS,
    DEFAULT_EPISODIC_PASSIVE_RECALL_MAX_CANDIDATES as _CFG_DEFAULT_EPISODIC_PASSIVE_RECALL_MAX_CANDIDATES,
    DEFAULT_RECENT_ACTIONS_LIMIT as _CFG_DEFAULT_RECENT_ACTIONS_LIMIT,
    DEFAULT_RECENT_OBSERVATIONS_LIMIT as _CFG_DEFAULT_RECENT_OBSERVATIONS_LIMIT,
    EpisodicRecallConfig,
    PromptBuilderCoreServices,
    PromptLimits,
    PromptSectionProviders,
)
# build_pre_turn_failure_section: Issue #227 chore β で廃止 (#241 後続)
# 詳細は build() 内コメント参照
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
        core: PromptBuilderCoreServices,
        *,
        sections: Optional[PromptSectionProviders] = None,
        episodic: Optional[EpisodicRecallConfig] = None,
        limits: Optional[PromptLimits] = None,
        ui_context_builder: Optional[ILlmUiContextBuilder] = None,
        current_tick_provider: Optional[Callable[[], Optional[int]]] = None,
    ) -> None:
        """Config dataclass ベースの API (Issue #227 後続 HIGH-1)。

        - ``core``: 必須インフラ群 (observation_buffer / world_query_service 等)
        - ``sections``: 任意 provider 群 (persona / objective / inventory / memo)
        - ``episodic``: 受動想起・記憶リンク・再解釈
        - ``limits``: 数値設定 + action_instruction + tile_map フラグ

        sections / episodic / limits は省略可能で、それぞれ「全フィールドが
        default」のインスタンスが使われる (= optional 機能はすべて無効)。
        """
        sections = sections or PromptSectionProviders()
        episodic = episodic or EpisodicRecallConfig()
        limits = limits or PromptLimits()

        # core は dataclass 自体が型 + non-Optional で表現するため、
        # 個別 isinstance 検証は最小限に絞る (Protocol 系のみ)
        if not isinstance(core, PromptBuilderCoreServices):
            raise TypeError("core must be PromptBuilderCoreServices")
        if not isinstance(sections, PromptSectionProviders):
            raise TypeError("sections must be PromptSectionProviders")
        if not isinstance(episodic, EpisodicRecallConfig):
            raise TypeError("episodic must be EpisodicRecallConfig")
        if not isinstance(limits, PromptLimits):
            raise TypeError("limits must be PromptLimits")

        # Issue #227 HIGH-3 Part 2: world_query_service / player_profile_repository は
        # 「DefaultPromptBuilder が呼ぶ 1〜2 メソッドを満たせばよい」duck-type 契約に
        # ゆるめる。escape_game runtime のような独自経路から adapter を差し込めるよう、
        # isinstance ではなく hasattr で構造チェックする。
        if not hasattr(core.world_query_service, "get_player_current_state"):
            raise TypeError(
                "core.world_query_service must have get_player_current_state method"
            )
        if not hasattr(core.player_profile_repository, "find_by_id"):
            raise TypeError(
                "core.player_profile_repository must have find_by_id method"
            )

        observation_buffer = core.observation_buffer
        sliding_window_memory = core.sliding_window_memory
        action_result_store = core.action_result_store
        world_query_service = core.world_query_service
        player_profile_repository = core.player_profile_repository
        current_state_formatter = core.current_state_formatter
        recent_events_formatter = core.recent_events_formatter
        context_format_strategy = core.context_format_strategy
        system_prompt_builder = core.system_prompt_builder
        available_tools_provider = core.available_tools_provider

        persona_block_provider = sections.persona_block_provider
        objective_text_provider = sections.objective_text_provider
        inventory_text_provider = sections.inventory_text_provider
        memo_store = sections.memo_store

        episodic_passive_recall = episodic.passive_recall
        episodic_passive_recall_limit_per_axis = episodic.passive_recall_limit_per_axis
        episodic_passive_recall_max_candidates = episodic.passive_recall_max_candidates
        episodic_memory_link_service = episodic.memory_link_service
        episodic_recall_buffer_store = episodic.recall_buffer_store
        episodic_reinterpretation_journal_store = episodic.reinterpretation_journal_store
        episodic_turn_index_provider = episodic.turn_index_provider

        recent_observations_limit = limits.recent_observations_limit
        recent_actions_limit = limits.recent_actions_limit
        default_action_instruction = limits.default_action_instruction
        tile_map_view_distance = limits.tile_map_view_distance
        tile_map_enabled = limits.tile_map_enabled
        memo_stale_age_ticks = limits.memo_stale_age_ticks
        if not isinstance(observation_buffer, IObservationContextBuffer):
            raise TypeError("observation_buffer must be IObservationContextBuffer")
        if not isinstance(sliding_window_memory, ISlidingWindowMemory):
            raise TypeError("sliding_window_memory must be ISlidingWindowMemory")
        if not isinstance(action_result_store, IActionResultStore):
            raise TypeError("action_result_store must be IActionResultStore")
        # world_query_service / player_profile_repository は __init__ 冒頭で
        # hasattr 構造チェック済み (Issue #227 HIGH-3 Part 2: duck-type 契約)
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
        if episodic_memory_link_service is not None and not isinstance(
            episodic_memory_link_service, EpisodicMemoryLinkApplicationService
        ):
            raise TypeError(
                "episodic_memory_link_service must be EpisodicMemoryLinkApplicationService or None"
            )
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
        if memo_store is not None and not isinstance(memo_store, IMemoStore):
            raise TypeError("memo_store must be IMemoStore or None")
        if current_tick_provider is not None and not callable(current_tick_provider):
            raise TypeError("current_tick_provider must be callable or None")
        if memo_stale_age_ticks < 0:
            raise ValueError("memo_stale_age_ticks must be 0 or greater")
        if objective_text_provider is not None and not callable(objective_text_provider):
            raise TypeError("objective_text_provider must be callable or None")
        if inventory_text_provider is not None and not callable(inventory_text_provider):
            raise TypeError("inventory_text_provider must be callable or None")

        self._memo_store = memo_store
        self._objective_text_provider = objective_text_provider
        self._inventory_text_provider = inventory_text_provider
        self._current_tick_provider = current_tick_provider
        self._memo_stale_age_ticks = memo_stale_age_ticks

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
        # Issue #227 PR-4 (tile-map 除去): spot_graph 専用ランタイムでは
        # include_tile_map=False でクエリを発行し、visible_tile_map と
        # current_terrain_type が常に None になるよう構造的に保証する。
        self._tile_map_enabled = tile_map_enabled
        self._episodic_passive_recall = episodic_passive_recall
        self._episodic_passive_recall_limit_per_axis = episodic_passive_recall_limit_per_axis
        self._episodic_passive_recall_max_candidates = episodic_passive_recall_max_candidates
        self._episodic_memory_link_service = episodic_memory_link_service
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
                include_tile_map=self._tile_map_enabled,
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
            recall_now = datetime.now(timezone.utc)
            recall_result = self._episodic_passive_recall.retrieve(
                player_id=player_id.value,
                situation_cues=situation_cues,
                limit_per_axis=self._episodic_passive_recall_limit_per_axis,
                max_candidates=self._episodic_passive_recall_max_candidates,
                now=recall_now,
            )
            relevant_memories_text = _join_passive_recall_texts(
                player_id.value,
                recall_result.candidates,
                self._episodic_reinterpretation_journal_store,
            )
            if self._episodic_memory_link_service is not None and recall_result.candidates:
                self._episodic_memory_link_service.on_passive_recall_candidates(
                    player_id.value,
                    recall_result.candidates,
                    now=recall_now,
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

        # 6c. 進行中のメモ (Issue #188 Phase 1a): LLM が memo_add で context に
        # 固定した未完了 memo を整形する。age + stale フラグで「古くなった
        # メモは review してほしい」を視覚化。
        active_memos_text = self._build_active_memos_text(player_id)

        # Issue #227 chore β: 実行ランタイム固有の固定目的文 + 所持物証テキスト
        # を provider 経由で取得 (escape_game format への統一)。
        # provider が落ちた場合は ERROR で記録した上で空文字に degrade する。
        # WARNING ではなく ERROR にする理由: provider 実装バグはサイレントに
        # 黙過すべきでなく、ログ集約側で必ず可視化したい (silent failure 防止)。
        # 一方で prompt 構築全体を中断するのは過剰なので degrade で続行する。
        objective_text = self._call_text_provider(
            self._objective_text_provider, player_id, "objective_text_provider"
        )
        inventory_text = self._call_text_provider(
            self._inventory_text_provider, player_id, "inventory_text_provider"
        )

        context = self._context_format_strategy.format(
            current_state_text=current_state_text,
            recent_events_text=recent_events_text,
            relevant_memories_text=relevant_memories_text,
            active_memos_text=active_memos_text,
            objective_text=objective_text,
            inventory_text=inventory_text,
        )

        # Issue #227 chore β: failure_block (直前ターン失敗時の補正セクション)
        # を廃止した。理由:
        #   1. 同じ失敗情報は ``recent_events_text`` (## 直近の出来事) に既に
        #      含まれている。重複表示で LLM の attention が拡散する。
        #   2. 「連続同一ツール失敗」の警告は PR #230 で導入した
        #      ``tool_call_loop_guard`` がより一般化して扱う (success / fail
        #      両方 / threshold 可変)。失敗専用のセクションは loop_guard で
        #      代替可能。
        # build_pre_turn_failure_section() を呼んでいた箇所はこの commit で削除。
        user_context_body = context.rstrip()

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

    def _build_active_memos_text(self, player_id: PlayerId) -> str:
        """LLM が固定した未完了 memo を「進行中のメモ」用テキストに整形する。

        Issue #188 Phase 1a:
        - memo_store 未注入なら空文字 (section ごと出さない)
        - 未完了メモがゼロなら空文字
        - 各 memo に age (経過 tick) と stale フラグを付与する
          (詳細は active_memos_formatter.format_active_memos に委譲)
        """
        if self._memo_store is None:
            return ""
        try:
            entries = self._memo_store.list_uncompleted(player_id)
        except Exception:
            return ""
        current_tick = (
            self._current_tick_provider()
            if self._current_tick_provider is not None
            else None
        )
        return format_active_memos(
            entries,
            current_tick=current_tick,
            stale_age_ticks=self._memo_stale_age_ticks,
        )

    def _call_text_provider(
        self,
        provider: Optional[Callable[[PlayerId], str]],
        player_id: PlayerId,
        provider_name: str,
    ) -> str:
        """provider を呼んで text を返す。落ちたら ERROR ログ + 空文字 degrade。

        provider バグを silent に握り潰すと debug が極めて困難になるため、
        ERROR レベル + exc_info=True でログ集約側に必ず可視化させる。
        prompt 構築自体は止めず degrade で続行する (provider は補助的な
        section なので、欠けても LLM ターン自体は成立する)。
        """
        if provider is None:
            return ""
        try:
            return provider(player_id) or ""
        except Exception:
            self._logger.error(
                "%s raised; degrading to empty text. Fix provider implementation.",
                provider_name,
                exc_info=True,
            )
            return ""
