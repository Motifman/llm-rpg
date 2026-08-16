"""1 ターン分のプロンプト組み立てのデフォルト実装"""

import logging
from importlib import import_module
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from ai_rpg_world.domain.being.value_object.being_id import BeingId
    from ai_rpg_world.application.llm.services.tool_call_loop_guard import (
        ToolCallLoopGuardService,
    )
from ai_rpg_world.application.llm.contracts.dtos import SystemPromptPlayerInfoDto
from ai_rpg_world.domain.memory.episodic.repository.episodic_recall_buffer_repository import EpisodicRecallBufferRepository
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import EpisodicRecallObservation
from ai_rpg_world.domain.memory.episodic.repository.episodic_reinterpretation_journal_repository import EpisodicReinterpretationJournalRepository
from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    IAvailableToolsProvider,
    IContextFormatStrategy,
    ICurrentStateFormatter,
    ILlmUiContextBuilder,
    IPromptBuilder,
    IRecentEventsFormatter,
    IShortTermMemory,
    ISystemPromptBuilder,
)
from ai_rpg_world.domain.memory.memo.repository.memo_repository import MemoRepository
from ai_rpg_world.domain.memory.memo.value_object.memo_entry import MemoEntry
from ai_rpg_world.application.llm.exceptions import PlayerProfileNotFoundForPromptException
from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.application.llm.services.active_memos_formatter import (
    format_active_memos,
)
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    EpisodicPassiveRecallRetrievalDebug,
    EpisodicPassiveRecallRetrievalService,
)
from ai_rpg_world.application.llm.services.prompt_sections.episodic_recall import (
    _R4_PER_TEXT_CHAR_CAP,
    _R4_RECENT_FREETEXT_LIMIT,
    _format_afterglow_section,
    _gather_additional_freetexts_for_recall,
    _join_passive_recall_texts,
    _module_logger,
    append_recall_observation,
    emit_episodic_recall_trace,
    run_episodic_passive_recall,
)
from ai_rpg_world.application.llm.services.prompt_sections.pending_predictions import (
    build_pending_predictions_text,
)
from ai_rpg_world.application.llm.services.prompt_sections.prediction_context import (
    attach_prediction_context,
    begin_prediction_context,
    emit_prediction_context_discarded_note,
)
from ai_rpg_world.application.llm.services.prompt_sections.prediction_feedback import (
    _PREDICTION_FEEDBACK_LEDGER_LIMIT,
    _PREDICTION_FEEDBACK_TOTAL_CHAR_CAP,
    build_prediction_feedback_text,
)
from ai_rpg_world.application.llm.services.prompt_sections.semantic_recall import (
    _gather_semantic_topic_words_for_recall,
    emit_semantic_passive_recall_trace,
    run_semantic_passive_recall,
)
from ai_rpg_world.application.llm.services.episodic_memory_link_application_service import (
    EpisodicMemoryLinkApplicationService,
)
from ai_rpg_world.application.llm.services.prediction_context_ledger import (
    PredictionContextLedger,
)
from ai_rpg_world.application.llm.services.unified_recent_event_store import (
    UnifiedRecentEventStore,
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
from ai_rpg_world.application.being.acting_being import ActingBeing
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


DEFAULT_ACTION_INSTRUCTION = "利用可能なツールで次の行動を選んでください。"
DEFAULT_RECENT_OBSERVATIONS_LIMIT = 20
DEFAULT_RECENT_ACTIONS_LIMIT = 20
DEFAULT_EPISODIC_PASSIVE_RECALL_LIMIT_PER_AXIS = 10
DEFAULT_EPISODIC_PASSIVE_RECALL_MAX_CANDIDATES = 10
MESSAGE_WHEN_PLAYER_NOT_PLACED = "現在地: 未配置。ゲームに参加するまで待機しています。"


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
        trace_recorder: Optional["ITraceRecorder"] = None,
        trace_recorder_provider: Optional[
            Callable[[], Optional["ITraceRecorder"]]
        ] = None,
        tool_call_loop_guard: Optional["ToolCallLoopGuardService"] = None,
        prediction_context_ledger: Optional[PredictionContextLedger] = None,
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
        # ゆるめる。world_runtime runtime のような独自経路から adapter を差し込めるよう、
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
        short_term_memory = core.short_term_memory
        action_result_store = core.action_result_store
        recent_event_store = core.recent_event_store
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
        # Issue #283 後続: 観測 prose 経由の自由文 cue 抽出マッチャ (任意)。
        noun_matcher = episodic.noun_matcher
        # Phase 1c: semantic memory の passive top-K (任意)。
        # service=None または top_k=0 なら prompt §「【関連する学び】」は出ない。
        semantic_passive_recall = episodic.semantic_passive_recall
        semantic_passive_top_k = episodic.semantic_passive_top_k
        # PR8 (R5): encounter memory を recall cue 源にする。注入時のみ動く。
        encounter_memory_for_recall = episodic.encounter_memory
        encounter_recent_window_ticks = episodic.encounter_recent_window_ticks
        # U10a (予測誤差統一設計 部品6・pending prediction): store が None なら
        # 機構自体が無効 (= 他の sidecar store と同じ「store の有無で判定」規約)。
        pending_prediction_store = episodic.pending_prediction_store
        pending_prediction_resurface_cap = episodic.pending_prediction_resurface_cap

        recent_observations_limit = limits.recent_observations_limit
        recent_actions_limit = limits.recent_actions_limit
        default_action_instruction = limits.default_action_instruction
        tile_map_view_distance = limits.tile_map_view_distance
        tile_map_enabled = limits.tile_map_enabled
        memo_stale_age_ticks = limits.memo_stale_age_ticks
        if not isinstance(observation_buffer, IObservationContextBuffer):
            raise TypeError("observation_buffer must be IObservationContextBuffer")
        if not isinstance(short_term_memory, IShortTermMemory):
            raise TypeError("short_term_memory must be IShortTermMemory")
        if not isinstance(action_result_store, IActionResultStore):
            raise TypeError("action_result_store must be IActionResultStore")
        if not isinstance(recent_event_store, UnifiedRecentEventStore):
            raise TypeError("recent_event_store must be UnifiedRecentEventStore")
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
            episodic_recall_buffer_store, EpisodicRecallBufferRepository
        ):
            raise TypeError(
                "episodic_recall_buffer_store must be EpisodicRecallBufferRepository or None"
            )
        if episodic_reinterpretation_journal_store is not None and not isinstance(
            episodic_reinterpretation_journal_store,
            EpisodicReinterpretationJournalRepository,
        ):
            raise TypeError(
                "episodic_reinterpretation_journal_store must be "
                "EpisodicReinterpretationJournalRepository or None"
            )
        if episodic_turn_index_provider is not None and not callable(
            episodic_turn_index_provider
        ):
            raise TypeError("episodic_turn_index_provider must be callable or None")
        # Phase 1c: semantic passive top-K の型検証 (import は service 構築時のみ
        # 必要なので遅延 import)。service=None または top_k=0 のときは validate 不要。
        if semantic_passive_recall is not None:
            from ai_rpg_world.application.llm.services.semantic_passive_recall_service import (
                SemanticPassiveRecallService,
            )
            if not isinstance(semantic_passive_recall, SemanticPassiveRecallService):
                raise TypeError(
                    "semantic_passive_recall must be SemanticPassiveRecallService or None"
                )
        if semantic_passive_top_k < 0:
            raise ValueError("semantic_passive_top_k must be 0 or greater")
        if memo_store is not None and not isinstance(memo_store, MemoRepository):
            raise TypeError("memo_store must be MemoRepository or None")
        if current_tick_provider is not None and not callable(current_tick_provider):
            raise TypeError("current_tick_provider must be callable or None")
        if memo_stale_age_ticks < 0:
            raise ValueError("memo_stale_age_ticks must be 0 or greater")
        if objective_text_provider is not None and not callable(objective_text_provider):
            raise TypeError("objective_text_provider must be callable or None")
        if inventory_text_provider is not None and not callable(inventory_text_provider):
            raise TypeError("inventory_text_provider must be callable or None")
        if trace_recorder is not None and not isinstance(trace_recorder, ITraceRecorder):
            raise TypeError("trace_recorder must be ITraceRecorder or None")
        if trace_recorder_provider is not None and not callable(trace_recorder_provider):
            raise TypeError("trace_recorder_provider must be callable or None")

        self._memo_store = memo_store
        # 直前ターンで同じ tool + 同じ引数を選ぼうとしているとき、その状態を
        # peek して instruction の先頭に専用警告を挟む (= attention 補強)。
        # loop_guard 本体の observation 注入は recent_events に並ぶので
        # 埋もれやすい。recency bias が効きやすい instruction の冒頭に
        # prepend して、LLM が「直前と同じ手」を選ぶ直前にもう一度気付く
        # きっかけを作る。None なら警告 prefix は出ない (= 既存挙動)。
        if tool_call_loop_guard is not None:
            from ai_rpg_world.application.llm.services.tool_call_loop_guard import (
                ToolCallLoopGuardService as _TCLGS,
            )
            if not isinstance(tool_call_loop_guard, _TCLGS):
                raise TypeError(
                    "tool_call_loop_guard must be ToolCallLoopGuardService or None"
                )
        self._tool_call_loop_guard = tool_call_loop_guard
        # U1: prediction_context_id を発行する ledger (任意)。None なら id 機構
        # 自体が OFF (= 既存挙動、result["prediction_context_id"] は常に None)。
        if prediction_context_ledger is not None and not isinstance(
            prediction_context_ledger, PredictionContextLedger
        ):
            raise TypeError(
                "prediction_context_ledger must be PredictionContextLedger or None"
            )
        self._prediction_context_ledger = prediction_context_ledger
        self._objective_text_provider = objective_text_provider
        self._inventory_text_provider = inventory_text_provider
        self._current_tick_provider = current_tick_provider
        self._memo_stale_age_ticks = memo_stale_age_ticks

        self._observation_buffer = observation_buffer
        self._short_term_memory = short_term_memory
        self._action_result_store = action_result_store
        self._recent_event_store = recent_event_store
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
        # #526 段階 2: 慣化 sidecar (任意)。default off。retrieve service 側
        # にも別途注入されており、prompt_builder 側は record_recall (書込)
        # のためにだけ参照する (retrieve は read-only)。
        self._episodic_recall_habituation_store = episodic.recall_habituation_store
        # #526 段階 3: 想起スロット sidecar (任意)。default off。retrieve service
        # 側にも別途注入されており、prompt_builder 側は apply_decision (書込)
        # のためにだけ参照する (retrieve は read-only)。
        self._episodic_recall_slot_store = episodic.recall_slot_store
        self._episodic_recall_slot_cooldown_ticks = (
            episodic.recall_slot_cooldown_ticks
        )
        # #526 段階 3 PR-C: afterglow index sidecar (任意)。default off。
        # retrieve service 側で apply_afterglow_policy の結果が
        # ``debug.afterglow_index`` に乗ってくるので、ここでは store.apply_decision
        # (書込) のためにだけ参照する。retrieve は read-only。
        self._afterglow_store = episodic.afterglow_store
        # U10a (予測誤差統一設計 部品6・pending prediction): 再浮上用 sidecar
        # (任意)。default off。store が None なら機構自体が無効。
        self._pending_prediction_store = pending_prediction_store
        self._pending_prediction_resurface_cap = pending_prediction_resurface_cap
        self._noun_matcher = noun_matcher
        # Phase 1c
        self._semantic_passive_recall = semantic_passive_recall
        self._semantic_passive_top_k = semantic_passive_top_k
        # PR8 (R5)
        self._encounter_memory_for_recall = encounter_memory_for_recall
        self._encounter_recent_window_ticks = encounter_recent_window_ticks
        self._trace_recorder = trace_recorder
        self._trace_recorder_provider = trace_recorder_provider
        self._logger = logging.getLogger(self.__class__.__name__)

    def _resolve_encounter_tick(self) -> Optional[int]:
        """PR8 (R5): encounter cue 抽出のための現在 tick を返す。

        - ``current_tick_provider`` 未注入なら None (= encounter cue は skip)
        - provider 例外時は None フォールバック (recall を止めない)
        - provider が int 以外を返したら None フォールバック (silent な
          recall 停止より「encounter cue が立たないだけ」に倒す)
        """
        if self._current_tick_provider is None:
            return None
        try:
            tick = self._current_tick_provider()
        except Exception:
            # encounter cue が立たなくなるため、provider 例外は warning で
            # 残す (`encounter_memory.get_records_for` 側と粒度を揃える)。
            self._logger.warning(
                "current_tick_provider raised; skipping encounter cue",
                exc_info=True,
            )
            return None
        if not isinstance(tick, int) or isinstance(tick, bool):
            return None
        return tick

    def _resolve_trace_recorder(self) -> Optional[ITraceRecorder]:
        """recall trace 用の recorder を runtime 時点で取得する。

        ``trace_recorder_provider`` があれば毎回 lookup (= 後付け差し込み
        対応)、なければ構築時固定値。provider 例外は None フォールバック
        (= recall は普段通り走り、trace 行だけ落ちる)。
        """
        if self._trace_recorder_provider is not None:
            try:
                return self._trace_recorder_provider()
            except Exception:
                # 通常 provider は単純な lambda なので例外は希。DI 化や
                # 動的解決を加えたときに silent に消えるのを防ぐため DEBUG
                # 級で痕跡を残す。
                self._logger.debug(
                    "trace_recorder_provider raised; skipping recall trace",
                    exc_info=True,
                )
                return None
        return self._trace_recorder

    def _emit_prompt_section_breakdown_trace(
        self,
        *,
        player_id: PlayerId,
        system_content: str,
        objective_text: str,
        current_state_text: str,
        active_memos_text: str,
        recent_events_text: str,
        relevant_memories_text: str,
        inventory_text: str,
        instruction: str,
        tools: List[Dict[str, Any]],
        user_content: str,
        prediction_feedback_text: str = "",
    ) -> None:
        """``PROMPT_SECTION_BREAKDOWN`` を 1 件記録する (失敗は握りつぶす)。

        prompt_builder.build() の末尾で 1 ターン 1 件呼ぶ。各 section の文字数を
        独立に計測することで、後続の prefix cache / token 分析で「どの section
        が prompt_tokens を支配しているか」が post-hoc に分かる。

        tools 配列は ``json.dumps`` でシリアライズした長さを使う。これは LLM
        API に送られる payload サイズの近似で、tool が動的に増減する効果を
        測れる。
        """
        recorder = self._resolve_trace_recorder()
        if recorder is None:
            return
        tick: Optional[int] = None
        if self._current_tick_provider is not None:
            try:
                tick = self._current_tick_provider()
            except Exception:
                tick = None
        try:
            import json as _json
            tools_chars = len(_json.dumps(tools, ensure_ascii=False))
        except Exception:
            tools_chars = 0
        try:
            recorder.record(
                TraceEventKind.PROMPT_SECTION_BREAKDOWN,
                tick=tick,
                player_id=int(player_id.value),
                system_chars=len(system_content),
                objective_chars=len(objective_text),
                current_state_chars=len(current_state_text),
                memos_chars=len(active_memos_text),
                prediction_feedback_chars=len(prediction_feedback_text),
                recent_events_chars=len(recent_events_text),
                recall_chars=len(relevant_memories_text),
                inventory_chars=len(inventory_text),
                instruction_chars=len(instruction),
                tools_chars=tools_chars,
                user_content_chars=len(user_content),
                messages_total_chars=len(system_content) + len(user_content),
                tools_count=len(tools),
            )
        except Exception:
            self._logger.debug(
                "trace recorder.record raised for PROMPT_SECTION_BREAKDOWN; skipping",
                exc_info=True,
            )

    def _emit_episodic_recall_trace(
        self,
        player_id: PlayerId,
        situation_cues: tuple,
        candidates: list,
        relevant_memories_text: str = "",
        retrieval_debug: Optional["EpisodicPassiveRecallRetrievalDebug"] = None,
    ) -> None:
        emit_episodic_recall_trace(
            self,
            player_id=player_id,
            situation_cues=situation_cues,
            candidates=candidates,
            relevant_memories_text=relevant_memories_text,
            retrieval_debug=retrieval_debug,
        )

    def _build_loop_warning_prefix(self, player_id: PlayerId) -> str:
        """instruction の前に挟む「同じ手の繰り返し」警告 prefix を返す。

        ``tool_call_loop_guard.peek_streak`` が連続 2 回以上を返したときだけ
        prefix を作る。それ以外は空文字。文面は recent_events に流れる
        loop_guard 警告と意図的に重ねて、両方の attention 経路を踏む。
        """
        if self._tool_call_loop_guard is None:
            return ""
        try:
            streak = self._tool_call_loop_guard.peek_streak(player_id)
        except Exception:
            return ""
        if streak is None:
            return ""
        tool_name, count = streak
        return (
            f"⚠ 直前のあなたは `{tool_name}` を同じ引数で {count} ターン連続"
            f"実行しました。同じ手を取れば同じ結果しか返りません。"
            f"「直近の出来事」のエラーメッセージや状況のヒントを読み返し、"
            f"別の選択肢 (引数を変える / 別のツールを使う / 周囲に尋ねる等) "
            f"を選んでください。"
        )

    def build(
        self,
        acting: ActingBeing,
        action_instruction: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not isinstance(acting, ActingBeing):
            raise TypeError("acting must be ActingBeing")
        if action_instruction is not None and not isinstance(action_instruction, str):
            raise TypeError("action_instruction must be str or None")
        player_id = acting.player_id
        being_id = acting.being_id

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
            overflow = self._short_term_memory.append_all(player_id, drained)

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
        observations = self._short_term_memory.get_recent(
            player_id, self._recent_observations_limit
        )
        action_results = self._action_result_store.get_recent(
            player_id, self._recent_actions_limit
        )
        recent_entries = self._recent_event_store.get_active_timeline(player_id)
        recent_events_text = self._recent_events_formatter.format_unified_entries(
            recent_entries
        )
        prediction_feedback_text = build_prediction_feedback_text(
            action_results, observations
        )
        # U10a (予測誤差統一設計 部品6・pending prediction): 保留中の予測の
        # 再浮上。store 未配線 (flag OFF) なら常に空文字 (= section 省略)。
        pending_predictions_text = self._build_pending_predictions_text(
            player_id=player_id,
            being_id=being_id,
            current_state_dto=current_state_dto,
        )

        # 5. 利用可能ツール取得
        tools = self._available_tools_provider.get_available_tools(current_state_dto)

        # U1 (二段階発行の 1 段目): passive recall より前に id を確保する。
        # こうすることで recall observation の生成時にこの id を stamp でき、
        # 「この episode を想起した prompt build で立てた予測」の紐付けが実在化
        # する (部品5 想起の信用割り当ての前提)。in-context 集合は recall 後に
        # 2 段目 (_attach_prediction_context) で確定する。ledger 未注入なら None。
        prediction_context_id = self._begin_prediction_context(player_id)

        # 6. 受動想起（任意注入）: runtime + 直近観測 structured から situation_cues → recall_text を連結
        relevant_memories_text, _passive_candidate_count, recalled_episode_ids = (
            self._run_passive_recall(
                player_id=player_id,
                being_id=being_id,
                observations=observations,
                action_results=action_results,
                ui_context=ui_context,
                current_state_text=current_state_text,
                recent_events_text=recent_events_text,
                player_info=player_info,
                current_state_dto=current_state_dto,
                prediction_context_id=prediction_context_id,
            )
        )

        # 6b. Phase 1c: semantic memory の passive top-K (任意)。
        # service=None または top_k=0 なら空文字を返し prompt §「【関連する学び】」
        # は出ない。状況連想キューは episodic 受動想起と同じ situation_cues を
        # 使う (関連 episodes と関連 semantic facts を同じ「いま」基準で集める)。
        learned_text, recalled_belief_ids = self._run_semantic_passive_recall(
            player_id=player_id,
            being_id=being_id,
            observations=observations,
            action_results=action_results,
            ui_context=ui_context,
            current_state_dto=current_state_dto,
        )

        # 6c. 進行中のメモ (Issue #188 Phase 1a): LLM が memo_add で context に
        # 固定した未完了 memo を整形する。age + stale フラグで「古くなった
        # メモは review してほしい」を視覚化。
        active_memos_text = self._build_active_memos_text(being_id)

        # Issue #227 chore β: 実行ランタイム固有の固定目的文 + 所持物証テキスト
        # を provider 経由で取得 (world_runtime format への統一)。
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

        # Phase 2: 短期記憶の L4 mid summary (rolling 実装のみが値を返す)。
        # 失敗しても prompt 構築を止めない。
        try:
            raw_mid = self._short_term_memory.get_mid_summary_text(player_id)
            mid_summary_text = raw_mid if isinstance(raw_mid, str) else ""
        except Exception as e:
            self._logger.warning(
                "get_mid_summary_text failed for player_id=%s: %s",
                player_id.value,
                e,
                exc_info=True,
            )
            mid_summary_text = ""

        # Phase 3: 短期記憶の L5 long summary (self_image / world_view)。
        try:
            raw_long = self._short_term_memory.get_long_summary_text(player_id)
            long_summary_text = raw_long if isinstance(raw_long, str) else ""
        except Exception as e:
            self._logger.warning(
                "get_long_summary_text failed for player_id=%s: %s",
                player_id.value,
                e,
                exc_info=True,
            )
            long_summary_text = ""

        context = self._context_format_strategy.format(
            current_state_text=current_state_text,
            recent_events_text=recent_events_text,
            relevant_memories_text=relevant_memories_text,
            active_memos_text=active_memos_text,
            objective_text=objective_text,
            inventory_text=inventory_text,
            learned_text=learned_text,
            mid_summary_text=mid_summary_text,
            long_summary_text=long_summary_text,
            prediction_feedback_text=prediction_feedback_text,
            pending_predictions_text=pending_predictions_text,
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
        # 7b. loop_guard 警告 prefix:
        # 直前ターンで同じ (tool, 引数) を選んでいた場合、instruction の
        # 直前に短い警告を挟む。recent_events に埋もれる loop_guard 観測と
        # 違い、instruction 末尾は LLM の attention が乗りやすい位置のため、
        # 「同じ手をもう一度選ぼうとしている」瞬間に気付かせやすい。
        loop_warning = self._build_loop_warning_prefix(player_id)
        if loop_warning:
            instruction = loop_warning + "\n\n" + instruction
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

        # U1 (二段階発行の 2 段目): 上で先に発行済みの prediction_context_id に、
        # この build で in-context だった episode_id / belief_id 群を後付けする。
        # ledger 未注入 (= id 機構 OFF) なら prediction_context_id は None で
        # attach も no-op (既存挙動)。
        self._attach_prediction_context(
            player_id=player_id,
            prediction_context_id=prediction_context_id,
            episode_ids=recalled_episode_ids,
            belief_ids=recalled_belief_ids,
        )
        result["prediction_context_id"] = prediction_context_id

        # 実験 #356 後続: prefix cache 分析用の section 別 char 内訳を trace に
        # 1 件記録する。token ではなく char で吐く理由はモジュール docstring 参照。
        self._emit_prompt_section_breakdown_trace(
            player_id=player_id,
            system_content=system_content,
            objective_text=objective_text,
            current_state_text=current_state_text,
            active_memos_text=active_memos_text,
            prediction_feedback_text=prediction_feedback_text,
            recent_events_text=recent_events_text,
            relevant_memories_text=relevant_memories_text,
            inventory_text=inventory_text,
            instruction=instruction,
            tools=tools,
            user_content=user_content,
        )
        return result

    def _begin_prediction_context(self, player_id: PlayerId) -> Optional[str]:
        return begin_prediction_context(self, player_id)

    def _attach_prediction_context(
        self,
        *,
        player_id: PlayerId,
        prediction_context_id: Optional[str],
        episode_ids: tuple[str, ...],
        belief_ids: tuple[str, ...],
    ) -> None:
        attach_prediction_context(
            self,
            player_id=player_id,
            prediction_context_id=prediction_context_id,
            episode_ids=episode_ids,
            belief_ids=belief_ids,
        )

    def _emit_prediction_context_discarded_note(
        self, *, player_id: PlayerId, discarded_id: str
    ) -> None:
        emit_prediction_context_discarded_note(
            self, player_id=player_id, discarded_id=discarded_id
        )

    def _run_passive_recall(
        self,
        *,
        player_id: PlayerId,
        being_id: BeingId,
        observations: List[ObservationEntry],
        action_results: List[Any],
        ui_context: Any,
        current_state_text: str,
        recent_events_text: str,
        player_info: SystemPromptPlayerInfoDto,
        current_state_dto: Optional[Any] = None,
        prediction_context_id: Optional[str] = None,
    ) -> tuple[str, Optional[int], tuple[str, ...]]:
        return run_episodic_passive_recall(
            self,
            player_id=player_id,
            being_id=being_id,
            observations=observations,
            action_results=action_results,
            ui_context=ui_context,
            current_state_text=current_state_text,
            recent_events_text=recent_events_text,
            player_info=player_info,
            current_state_dto=current_state_dto,
            prediction_context_id=prediction_context_id,
        )

    def _run_semantic_passive_recall(
        self,
        *,
        player_id: PlayerId,
        being_id: BeingId,
        observations: List[ObservationEntry],
        action_results: List[Any],
        ui_context: Any,
        current_state_dto: Optional[Any] = None,
    ) -> tuple[str, tuple[str, ...]]:
        return run_semantic_passive_recall(
            self,
            player_id=player_id,
            being_id=being_id,
            observations=observations,
            action_results=action_results,
            ui_context=ui_context,
            current_state_dto=current_state_dto,
        )

    def _emit_semantic_passive_recall_trace(
        self,
        *,
        player_id: PlayerId,
        situation_cues: tuple,
        candidates: list,
    ) -> None:
        emit_semantic_passive_recall_trace(
            self,
            player_id=player_id,
            situation_cues=situation_cues,
            candidates=candidates,
        )

    def _build_pending_predictions_text(
        self,
        *,
        player_id: PlayerId,
        being_id: BeingId,
        current_state_dto: Optional[Any],
    ) -> str:
        return build_pending_predictions_text(
            self,
            player_id=player_id,
            being_id=being_id,
            current_state_dto=current_state_dto,
        )

    def _append_recall_observation(
        self,
        being_id: Optional["BeingId"],
        observation: "EpisodicRecallObservation",
    ) -> None:
        append_recall_observation(self, being_id, observation)

    def _fetch_uncompleted_memos(self, being_id: BeingId) -> list[MemoEntry]:
        """being_id 経路で未完了 memo を引く (Phase 3 Step 3a-3)。

        呼び出し側 (手番入口) が ``ActingBeing.being_id`` を渡す前提。
        """
        assert self._memo_store is not None
        return self._memo_store.list_uncompleted_by_being(being_id)

    def _build_active_memos_text(self, being_id: BeingId) -> str:
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
            entries = self._fetch_uncompleted_memos(being_id)
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
