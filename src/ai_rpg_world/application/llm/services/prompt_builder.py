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
from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
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


_module_logger = logging.getLogger(__name__)


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
                # 再解釈 store の障害で recall を止めず生の recall_text に縮退する。
                # 「sail と active が drift している」状況を後追いできるよう WARN
                # で traceback ごと残す (silent failure 防止)。
                _module_logger.warning(
                    "journal_store.get_active failed for player=%s episode=%s; "
                    "falling back to raw recall_text",
                    player_id,
                    cand.episode.episode_id,
                    exc_info=True,
                )
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
        trace_recorder: Optional["ITraceRecorder"] = None,
        trace_recorder_provider: Optional[
            Callable[[], Optional["ITraceRecorder"]]
        ] = None,
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
        # Issue #283 後続: 観測 prose 経由の自由文 cue 抽出マッチャ (任意)。
        noun_matcher = episodic.noun_matcher
        # Phase 1c: semantic memory の passive top-K (任意)。
        # service=None または top_k=0 なら prompt §「【関連する学び】」は出ない。
        semantic_passive_recall = episodic.semantic_passive_recall
        semantic_passive_top_k = episodic.semantic_passive_top_k

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
        if trace_recorder is not None and not isinstance(trace_recorder, ITraceRecorder):
            raise TypeError("trace_recorder must be ITraceRecorder or None")
        if trace_recorder_provider is not None and not callable(trace_recorder_provider):
            raise TypeError("trace_recorder_provider must be callable or None")

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
        self._noun_matcher = noun_matcher
        # Phase 1c
        self._semantic_passive_recall = semantic_passive_recall
        self._semantic_passive_top_k = semantic_passive_top_k
        self._trace_recorder = trace_recorder
        self._trace_recorder_provider = trace_recorder_provider
        self._logger = logging.getLogger(self.__class__.__name__)

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
    ) -> None:
        """``EPISODIC_RECALL`` を trace に記録する (失敗は握りつぶす)。

        ``relevant_memories_text`` は実 prompt に注入された連結後テキスト。
        recall 1 件あたりの注入サイズ ÷ prompt_tokens を post-hoc に出すための
        計測点 (実験 #356 後続: cached_tokens / TTFT 分析と組合せる)。
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
            cue_keys = [c.to_canonical() for c in situation_cues]
        except Exception:
            cue_keys = []
        cand_payload: list[dict] = []
        for cand in candidates:
            try:
                ep = cand.episode
                cand_payload.append(
                    {
                        "episode_id": getattr(ep, "episode_id", ""),
                        "source_axes": list(cand.source_axes),
                        "recall_text_snippet": (getattr(ep, "recall_text", "") or "")[:120],
                    }
                )
            except Exception:
                continue
        try:
            recorder.record(
                TraceEventKind.EPISODIC_RECALL,
                tick=tick,
                player_id=int(player_id.value),
                situation_cues=cue_keys,
                candidate_count=len(cand_payload),
                candidates=cand_payload,
                recall_text_chars_total=len(relevant_memories_text or ""),
            )
        except Exception:
            # 例: recorder が新しい kind を未知扱いで例外を投げる等。
            # prompt build を止めない方針を維持しつつ、recorder 側のバグを
            # 後追いできるよう DEBUG 級で痕跡を残す (logger は親クラスから)。
            self._logger.debug(
                "trace recorder.record raised for EPISODIC_RECALL; skipping",
                exc_info=True,
            )

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
        relevant_memories_text = self._run_passive_recall(
            player_id=player_id,
            observations=observations,
            action_results=action_results,
            ui_context=ui_context,
            current_state_text=current_state_text,
            recent_events_text=recent_events_text,
            player_info=player_info,
        )

        # 6b. Phase 1c: semantic memory の passive top-K (任意)。
        # service=None または top_k=0 なら空文字を返し prompt §「【関連する学び】」
        # は出ない。状況連想キューは episodic 受動想起と同じ situation_cues を
        # 使う (関連 episodes と関連 semantic facts を同じ「いま」基準で集める)。
        learned_text = self._run_semantic_passive_recall(
            player_id=player_id,
            observations=observations,
            action_results=action_results,
            ui_context=ui_context,
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

        # Phase 2: 短期記憶の L4 mid summary (rolling 実装のみが値を返す)。
        # 失敗しても prompt 構築を止めない。
        try:
            raw_mid = self._sliding_window.get_mid_summary_text(player_id)
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
            raw_long = self._sliding_window.get_long_summary_text(player_id)
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

        # 実験 #356 後続: prefix cache 分析用の section 別 char 内訳を trace に
        # 1 件記録する。token ではなく char で吐く理由はモジュール docstring 参照。
        self._emit_prompt_section_breakdown_trace(
            player_id=player_id,
            system_content=system_content,
            objective_text=objective_text,
            current_state_text=current_state_text,
            active_memos_text=active_memos_text,
            recent_events_text=recent_events_text,
            relevant_memories_text=relevant_memories_text,
            inventory_text=inventory_text,
            instruction=instruction,
            tools=tools,
            user_content=user_content,
        )
        return result

    def _run_passive_recall(
        self,
        *,
        player_id: PlayerId,
        observations: List[ObservationEntry],
        action_results: List[Any],
        ui_context: Any,
        current_state_text: str,
        recent_events_text: str,
        player_info: SystemPromptPlayerInfoDto,
    ) -> str:
        """受動想起ブロックを実行し、関連する記憶テキストを返す。

        Issue #227 後続レビュー (Prompt MEDIUM-5) で build() 本体から抽出。
        responsibilities:
        1. situation_cues を runtime_context + 直近観測 + 直近 action から組む
        2. passive_recall.retrieve で候補 episode を取得
        3. 候補を改行で連結して relevant_memories_text を作る
        4. memory_link_service があれば passive recall 通知を流す
        5. recall_buffer_store があれば EpisodicRecallObservation を append

        passive_recall が未注入なら何もせず空文字を返す。
        """
        if self._episodic_passive_recall is None:
            return ""

        observation_structured = None
        observation_prose: str | None = None
        if observations:
            observation_structured = observations[0].output.structured
            observation_prose = observations[0].output.prose
        latest_action = action_results[0] if action_results else None
        situation_cues = build_situation_episodic_cues(
            runtime_context=ui_context.tool_runtime_context,
            observation_structured=observation_structured,
            latest_action=latest_action,
            observation_prose=observation_prose,
            noun_matcher=self._noun_matcher,
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

        # Issue #283 後続: recall 結果を trace に残す (Viewer / jq から
        # 「どのエピソードが想起されたか」を後追いできる)。candidates が 0
        # でも「recall を試行したが結果は 0」事実は残しておく価値があるので emit。
        self._emit_episodic_recall_trace(
            player_id=player_id,
            situation_cues=situation_cues,
            candidates=list(recall_result.candidates),
            relevant_memories_text=relevant_memories_text,
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

        return relevant_memories_text

    def _run_semantic_passive_recall(
        self,
        *,
        player_id: PlayerId,
        observations: List[ObservationEntry],
        action_results: List[Any],
        ui_context: Any,
    ) -> str:
        """Phase 1c: semantic memory の状況連想 top-K を §「【関連する学び】」用に整形する。

        service 未注入 または top_k=0 なら空文字 (= section ごと省略)。
        situation_cues は episodic 受動想起と同じ build_situation_episodic_cues
        を使う (関連 episodes と関連 semantic facts を同じ「いま」基準で集める)。
        """
        if self._semantic_passive_recall is None or self._semantic_passive_top_k <= 0:
            return ""

        observation_structured = None
        observation_prose: Optional[str] = None
        if observations:
            observation_structured = observations[0].output.structured
            observation_prose = observations[0].output.prose
        latest_action = action_results[0] if action_results else None
        situation_cues = build_situation_episodic_cues(
            runtime_context=ui_context.tool_runtime_context,
            observation_structured=observation_structured,
            latest_action=latest_action,
            observation_prose=observation_prose,
            noun_matcher=self._noun_matcher,
        )
        now = datetime.now(timezone.utc)
        try:
            candidates = self._semantic_passive_recall.retrieve(
                player_id=player_id.value,
                situation_cues=situation_cues,
                top_k=self._semantic_passive_top_k,
                now=now,
            )
        except Exception as e:
            # semantic ランキング失敗で prompt build を止めない
            self._logger.warning(
                "Semantic passive recall failed for player_id=%s: %s",
                player_id.value,
                e,
                exc_info=True,
            )
            candidates = []

        self._emit_semantic_passive_recall_trace(
            player_id=player_id,
            situation_cues=situation_cues,
            candidates=candidates,
        )

        from ai_rpg_world.application.llm.services.semantic_passive_recall_service import (
            format_semantic_recall_section,
        )
        return format_semantic_recall_section(candidates)

    def _emit_semantic_passive_recall_trace(
        self,
        *,
        player_id: PlayerId,
        situation_cues: tuple,
        candidates: list,
    ) -> None:
        """``SEMANTIC_PASSIVE_RECALL`` を 1 件 emit する (失敗は握りつぶす)。

        Phase 1c 計測点: どの semantic entry が top-K に入り、それぞれの
        score 内訳 (recency / importance / relevance) を後追いできるようにする。
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
            cue_keys = [c.to_canonical() for c in situation_cues]
        except Exception:
            cue_keys = []
        cand_payload: list[dict] = []
        for cand in candidates:
            try:
                cand_payload.append(cand.to_trace_payload())
            except Exception:
                continue
        try:
            recorder.record(
                TraceEventKind.SEMANTIC_PASSIVE_RECALL,
                tick=tick,
                player_id=int(player_id.value),
                situation_cues=cue_keys,
                top_k=int(self._semantic_passive_top_k),
                candidate_count=len(cand_payload),
                candidates=cand_payload,
            )
        except Exception:
            self._logger.debug(
                "trace recorder.record raised for SEMANTIC_PASSIVE_RECALL; skipping",
                exc_info=True,
            )

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
