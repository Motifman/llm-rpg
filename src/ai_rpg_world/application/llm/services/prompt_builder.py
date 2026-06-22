"""1 ターン分のプロンプト組み立てのデフォルト実装"""

import logging
from datetime import datetime, timezone
from importlib import import_module
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

if TYPE_CHECKING:
    from ai_rpg_world.domain.being.service.being_attachment_resolver import (
        BeingAttachmentResolver,
    )
    from ai_rpg_world.domain.being.value_object.being_id import BeingId
    from ai_rpg_world.domain.world.value_object.world_id import WorldId
from uuid import uuid4

from ai_rpg_world.application.llm.contracts.dtos import (
    ActionResultEntry,
    SystemPromptPlayerInfoDto,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import EpisodicRecallObservation
from ai_rpg_world.domain.memory.episodic.repository.episodic_recall_buffer_repository import EpisodicRecallBufferRepository
from ai_rpg_world.domain.memory.episodic.repository.episodic_reinterpretation_journal_repository import EpisodicReinterpretationJournalRepository
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
from ai_rpg_world.domain.memory.memo.repository.memo_repository import MemoRepository
from ai_rpg_world.domain.memory.memo.value_object.memo_entry import MemoEntry
from ai_rpg_world.application.llm.exceptions import PlayerProfileNotFoundForPromptException
from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.application.llm.services.active_memos_formatter import (
    format_active_memos,
)
from ai_rpg_world.application.llm.services.episodic_cue_rules import build_situation_episodic_cues
from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
    EpisodicPassiveRecallCandidate,
    EpisodicPassiveRecallRetrievalDebug,
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

# PR7 (R4): noun_matcher に通す追加テキストの上限。直近 N 件の観測 / 行動結果
# を対象にする。長すぎる prose は per-text char cap で打ち切り、Aho-Corasick
# の線形性を信じても pathological 入力で時間爆発しないようにする。
_R4_RECENT_FREETEXT_LIMIT = 5
_R4_PER_TEXT_CHAR_CAP = 2048
_PREDICTION_FEEDBACK_FOLLOWUP_OBSERVATION_LIMIT = 2


_module_logger = logging.getLogger(__name__)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _nonempty_text(raw: Any) -> str | None:
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    return text or None


def build_prediction_feedback_text(
    action_results: List[ActionResultEntry],
    observations: List[ObservationEntry],
) -> str:
    """最新の予測付き action を、実際の結果と並べる prompt section 本文にする。"""

    if not isinstance(action_results, list):
        raise TypeError("action_results must be list")
    if not isinstance(observations, list):
        raise TypeError("observations must be list")
    for entry in action_results:
        if not isinstance(entry, ActionResultEntry):
            raise TypeError("action_results must contain only ActionResultEntry")
    for obs in observations:
        if not isinstance(obs, ObservationEntry):
            raise TypeError("observations must contain only ObservationEntry")

    predicted_action: ActionResultEntry | None = None
    expected: str | None = None
    for entry in sorted(action_results, key=lambda e: _as_utc(e.occurred_at), reverse=True):
        expected = _nonempty_text(getattr(entry, "expected_result", None))
        if expected is not None:
            predicted_action = entry
            break
    if predicted_action is None or expected is None:
        return ""

    action_at = _as_utc(predicted_action.occurred_at)
    followups: list[str] = []
    for obs in sorted(observations, key=lambda e: _as_utc(e.occurred_at)):
        if _as_utc(obs.occurred_at) <= action_at:
            continue
        prose = _nonempty_text(obs.output.prose)
        if prose is None:
            continue
        followups.append(prose)
        if len(followups) >= _PREDICTION_FEEDBACK_FOLLOWUP_OBSERVATION_LIMIT:
            break

    tool = _nonempty_text(predicted_action.tool_name) or "unknown_tool"
    status = "success=True" if predicted_action.success else "success=False"
    actual_parts = [f"tool={tool}", status]
    if not predicted_action.success and predicted_action.error_code:
        actual_parts.append(f"error_code={predicted_action.error_code}")
    result_summary = _nonempty_text(predicted_action.result_summary)
    if result_summary is not None:
        actual_parts.append(f"result={result_summary}")

    lines = [
        "前回の予測を、願望ではなく世界への仮説として読み直してください。",
        f"- 予測: {expected}",
        f"- 実際: {' / '.join(actual_parts)}",
    ]
    if followups:
        lines.append("- 後続観測:")
        lines.extend(f"  - {text}" for text in followups)
    return "\n".join(lines)


def _gather_additional_freetexts_for_recall(
    observations: List[ObservationEntry],
    action_results: List[ActionResultEntry],
) -> list[str]:
    """PR7 (R4): recall 用に noun_matcher に通す追加文字列を集める。

    対象:
    - 直近 ``_R4_RECENT_FREETEXT_LIMIT`` 件の観測 prose ([1:] = 最新を除く。
      最新は別途 ``observation_prose`` として渡されるため重複させない)
    - 直近 ``_R4_RECENT_FREETEXT_LIMIT`` 件の行動結果の action_summary +
      result_summary (= 自分の speech / inner_thought / その他ツール発話の
      文字列)

    NOTE: ``action_results[0]`` は ``build_situation_episodic_cues`` に
    ``latest_action`` として別途渡されるが、そちらの経路は tool_name と outcome
    の cue を立てるだけで **action_summary / result_summary の自由文に対しては
    noun_matcher を当てない**。よってここで `[0]` を含めるのが正しい (= noun
    抽出パスはこちらが唯一)。下流 ``_validate_and_dedupe`` で重複 cue は 1 件化
    されるので最終 cue 列に重複は出ない。

    各テキストは ``_R4_PER_TEXT_CHAR_CAP`` 文字に切る (pathological prose
    での matcher 時間爆発を避ける safety cap)。
    """
    out: list[str] = []
    # observations は新しい順なので [0] は除いて [1:LIMIT+1] を取る
    for entry in observations[1 : _R4_RECENT_FREETEXT_LIMIT + 1]:
        prose = entry.output.prose
        if prose:
            out.append(prose[:_R4_PER_TEXT_CHAR_CAP])
    for ar in action_results[:_R4_RECENT_FREETEXT_LIMIT]:
        if ar.action_summary:
            out.append(ar.action_summary[:_R4_PER_TEXT_CHAR_CAP])
        if ar.result_summary:
            out.append(ar.result_summary[:_R4_PER_TEXT_CHAR_CAP])
    return out


def _format_afterglow_section(
    afterglow_index: Optional[tuple[Any, ...]],
) -> str:
    """afterglow index を 1 行見出しの section text に整形する。

    None / 空のときは空文字を返し、上位は section ごと省略する。各エントリは
    ``[handle] heading`` 形式の 1 行で並べ、LLM から「ぼんやり覚えてる
    記憶」として visible にする。handle は make_afterglow_handle で生成され、
    同じ episode は常に同じ handle になる (= 後続 PR の能動想起ツールで
    安定して引ける)。
    """
    if not afterglow_index:
        return ""
    # 関数内 import で循環依存を避ける
    from ai_rpg_world.application.llm.services.afterglow_store import (
        make_afterglow_handle,
    )

    lines = ["【さっき思い出した記憶の見出し】(鮮明には浮かばないが、ヒントとして残っている)"]
    for entry in afterglow_index:
        handle = make_afterglow_handle(entry.episode_id)
        lines.append(f"- [{handle}] {entry.heading}")
    return "\n".join(lines)


def _join_passive_recall_texts(
    player_id: int,
    candidates: tuple[EpisodicPassiveRecallCandidate, ...],
    journal_store: EpisodicReinterpretationJournalRepository | None = None,
    *,
    being_id: Optional["BeingId"] = None,
) -> str:
    """retrieve の候補順のまま、active 再解釈を優先して recall text を改行で連結する。

    Phase 3 Step 3d-3: legacy player_id 経路は撤去済。``being_id`` が ``None``
    の場合は journal をスキップして生の ``recall_text`` を使う (= prompt
    強化の graceful degradation)。``journal_store`` 自体が ``None`` の場合も
    同じく生 recall に縮退する。

    ``player_id`` は warning ログ用に保持 (journal 走査は being_id 経由のみ)。
    後続フェーズで Being の player_id 逆引きが容易になった場合は引数から
    削除可能。
    """
    parts: list[str] = []
    for cand in candidates:
        active = None
        if journal_store is not None and being_id is not None:
            try:
                active = journal_store.get_active_by_being(
                    being_id, cand.episode.episode_id
                )
            except Exception:
                # 再解釈 store の障害で recall を止めず生の recall_text に縮退する。
                # 「sail と active が drift している」状況を後追いできるよう WARN
                # で traceback ごと残す (silent failure 防止)。
                _module_logger.warning(
                    "journal_store.get_active_by_being failed for player=%s "
                    "episode=%s; falling back to raw recall_text",
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
        being_attachment_resolver: Optional["BeingAttachmentResolver"] = None,
        default_world_id: Optional["WorldId"] = None,
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
        # PR8 (R5): encounter memory を recall cue 源にする。注入時のみ動く。
        encounter_memory_for_recall = episodic.encounter_memory
        encounter_recent_window_ticks = episodic.encounter_recent_window_ticks

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
        # Phase 3 Step 3a-3: Resolver/WorldId は constructor では Optional のまま。
        # 未注入のときは ``_fetch_uncompleted_memos`` が空 list を返して
        # graceful 縮退する (= prompt 内 memo セクションが「未完了なし」表示)。
        # 詳細は _fetch_uncompleted_memos の docstring を参照。
        from ai_rpg_world.domain.being.service.being_attachment_resolver import (
            BeingAttachmentResolver as _BAR,
        )
        from ai_rpg_world.domain.world.value_object.world_id import (
            WorldId as _WI,
        )
        if being_attachment_resolver is not None and not isinstance(
            being_attachment_resolver, _BAR
        ):
            raise TypeError(
                "being_attachment_resolver must be BeingAttachmentResolver"
            )
        if default_world_id is not None and not isinstance(default_world_id, _WI):
            raise TypeError("default_world_id must be WorldId")
        self._being_attachment_resolver = being_attachment_resolver
        self._default_world_id = default_world_id
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
        retrieval_debug: Optional[EpisodicPassiveRecallRetrievalDebug] = None,
    ) -> None:
        """``EPISODIC_RECALL`` を trace に記録する (失敗は握りつぶす)。

        ``relevant_memories_text`` は実 prompt に注入された連結後テキスト。
        recall 1 件あたりの注入サイズ ÷ prompt_tokens を post-hoc に出すための
        計測点 (実験 #356 後続: cached_tokens / TTFT 分析と組合せる)。

        ``retrieval_debug`` が与えられれば、検索 axis ごとの raw 件数・
        max_cap 前 union 件数・最終 candidate の source_axes 別件数を
        payload に追加で乗せる (#526 後続: cue 設計の post-hoc 解析用)。
        既定 ``None`` のときは payload に追加キーを足さず、既存の trace
        読み手 (viewer / jq クエリ) を壊さない。
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
        # debug 由来の追加キーは ``retrieval_debug`` が与えられたときだけ
        # 載せる (= 既存 trace 読み手の non-strict 互換)。
        debug_kwargs: dict = {}
        if retrieval_debug is not None:
            try:
                debug_kwargs["raw_row_count_by_axis"] = {
                    axis: count for axis, count in retrieval_debug.raw_row_count_by_axis
                }
                debug_kwargs["union_episode_count_before_max_cap"] = (
                    retrieval_debug.union_episode_count_before_max_cap
                )
                debug_kwargs["final_episode_count_by_source_axis"] = {
                    axis: count
                    for axis, count in retrieval_debug.final_episode_count_by_source_axis
                }
                # #526 段階 2 (PR #565) 続き: 慣化ペナルティが適用された
                # episode の (id → penalty 値) も載せる。PR #565 で dataclass
                # field は追加されたが本 emission code は更新漏れだったため、
                # ペナルティが trace から見えず「慣化が動いているか」の判定が
                # 不可能になっていた。
                debug_kwargs["habituation_penalty_by_episode"] = {
                    eid: penalty
                    for eid, penalty in retrieval_debug.habituation_penalty_by_episode
                }
                # #526 段階 3: 想起スロットの 1 tick 分の動きを trace に残す。
                # off 時は decision=None なので何も書かない (= 既存挙動)。
                slot_decision = retrieval_debug.recall_slot_decision
                if slot_decision is not None:
                    debug_kwargs["recall_slot"] = {
                        "retained": [
                            {"episode_id": e.episode_id, "entered_tick": e.entered_tick}
                            for e in slot_decision.retained
                        ],
                        "inserted": [
                            {"episode_id": e.episode_id, "entered_tick": e.entered_tick}
                            for e in slot_decision.inserted
                        ],
                        "evicted_ids": list(slot_decision.evicted_ids),
                        "new_slot_size": len(slot_decision.new_slot),
                    }
                # #526 段階 3 PR-C: afterglow index の状態を trace に乗せる。
                # off 時は index=None なので key 自体を出さない (= 既存挙動)。
                afterglow_index = retrieval_debug.afterglow_index
                if afterglow_index is not None:
                    debug_kwargs["afterglow"] = {
                        "size": len(afterglow_index),
                        "entries": [
                            {
                                "episode_id": e.episode_id,
                                "heading": e.heading,
                                "entered_tick": e.entered_tick,
                                "source": e.source.value,
                            }
                            for e in afterglow_index
                        ],
                    }
            except Exception:
                # debug 構造が想定外でも recall trace 本体は落とさない。
                self._logger.debug(
                    "retrieval_debug の payload 化に失敗; 既存キーのみで emit します",
                    exc_info=True,
                )
                debug_kwargs = {}
        try:
            recorder.record(
                TraceEventKind.EPISODIC_RECALL,
                tick=tick,
                player_id=int(player_id.value),
                situation_cues=cue_keys,
                candidate_count=len(cand_payload),
                candidates=cand_payload,
                recall_text_chars_total=len(relevant_memories_text or ""),
                **debug_kwargs,
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
        prediction_feedback_text = build_prediction_feedback_text(
            action_results, observations
        )

        # 5. 利用可能ツール取得
        tools = self._available_tools_provider.get_available_tools(current_state_dto)

        # 6. 受動想起（任意注入）: runtime + 直近観測 structured から situation_cues → recall_text を連結
        relevant_memories_text, _passive_candidate_count = self._run_passive_recall(
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
            prediction_feedback_text=prediction_feedback_text,
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
            prediction_feedback_text=prediction_feedback_text,
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
    ) -> tuple[str, Optional[int]]:
        """受動想起ブロックを実行し、(関連する記憶テキスト, 候補件数) を返す。

        Issue #227 後続レビュー (Prompt MEDIUM-5) で build() 本体から抽出。
        responsibilities:
        1. situation_cues を runtime_context + 直近観測 + 直近 action から組む
        2. passive_recall.retrieve で候補 episode を取得
        3. 候補を改行で連結して relevant_memories_text を作る
        4. memory_link_service があれば passive recall 通知を流す
        5. recall_buffer_store があれば EpisodicRecallObservation を append

        候補件数は ``None`` で 「機構自体が未注入」 を表す (= 「0 件しか
        浮かばなかった」 と意味が異なる)。 ``int`` で 「機構は走ったが N 件」
        を表す。 sentinel int を避けて Optional で区別する。
        """
        if self._episodic_passive_recall is None:
            return "", None

        observation_structured = None
        observation_prose: str | None = None
        if observations:
            observation_structured = observations[0].output.structured
            observation_prose = observations[0].output.prose
        latest_action = action_results[0] if action_results else None
        additional_freetexts = _gather_additional_freetexts_for_recall(
            observations, action_results
        )
        encounter_tick = self._resolve_encounter_tick()
        situation_cues = build_situation_episodic_cues(
            runtime_context=ui_context.tool_runtime_context,
            observation_structured=observation_structured,
            latest_action=latest_action,
            observation_prose=observation_prose,
            noun_matcher=self._noun_matcher,
            additional_freetexts=additional_freetexts,
            encounter_memory=self._encounter_memory_for_recall,
            encounter_player_id=player_id,
            encounter_current_tick=encounter_tick,
            encounter_recent_window_ticks=self._encounter_recent_window_ticks,
        )
        recall_now = datetime.now(timezone.utc)
        # PR5 (R1): sliding window にまだ生きている直近 episode を recall から
        # 排除するため、最古 entry の occurred_at を時間下限として渡す。entry
        # が空のとき (= 起動直後) は None。安全 floor (= 最低 5 tick / scenario の
        # 1 tick 相当秒に変換) は加味せず、現時点の最古 entry 自身を境界に
        # 倒す。「境界 episode 自身は recall から外す」という保守的な側に倒す。
        #
        # 防衛: 旧 ISlidingWindowMemory 実装やテスト mock が default で None /
        # 不正な型を返すことがある。``None`` 以外で ``datetime`` でなければ、
        # 「実装側のバグ」として warning ログを残し、recall の時間下限フィルタを
        # off に倒す。silent fallback ではなく "noisy" な degradation にして、
        # ログから発見できるようにする。
        raw_oldest = self._sliding_window.get_oldest_entry_datetime(player_id)
        if raw_oldest is not None and not isinstance(raw_oldest, datetime):
            _module_logger.warning(
                "ISlidingWindowMemory.get_oldest_entry_datetime returned "
                "unexpected type %s for player_id=%s; recall の時間下限フィルタ "
                "を off にして fallback します。",
                type(raw_oldest).__name__,
                player_id.value,
            )
            raw_oldest = None
        min_recall_dt: Optional[datetime] = raw_oldest
        # #526 段階 2: 慣化ペナルティのため現在 tick を retrieve に渡す。
        # provider が None / 例外を返したときは慣化を skip (= 既存挙動)。
        current_tick_for_habituation: Optional[int] = None
        if self._current_tick_provider is not None:
            try:
                tick_val = self._current_tick_provider()
                if isinstance(tick_val, int) and not isinstance(tick_val, bool):
                    current_tick_for_habituation = tick_val
            except Exception:
                self._logger.debug(
                    "current_tick_provider raised; habituation を skip して進む",
                    exc_info=True,
                )
        recall_result = self._episodic_passive_recall.retrieve(
            player_id=player_id.value,
            situation_cues=situation_cues,
            limit_per_axis=self._episodic_passive_recall_limit_per_axis,
            max_candidates=self._episodic_passive_recall_max_candidates,
            now=recall_now,
            min_occurred_at=min_recall_dt,
            current_tick=current_tick_for_habituation,
        )
        being_id = self._resolve_being_id(player_id)
        relevant_memories_text = _join_passive_recall_texts(
            player_id.value,
            recall_result.candidates,
            self._episodic_reinterpretation_journal_store,
            being_id=being_id,
        )

        # #526 段階 3 PR-C: afterglow index を 1 行見出しの section として連結。
        # 「鮮明な記憶」(= recall_text の本文) の後ろに「さっき思い出した記憶の
        # 見出し」を並べ、LLM に「ぼんやり覚えてる」の層が見える形にする。
        # afterglow off / 空のときは何も足さない。
        afterglow_text = _format_afterglow_section(
            recall_result.debug.afterglow_index
        )
        if afterglow_text:
            if relevant_memories_text:
                relevant_memories_text = (
                    f"{relevant_memories_text}\n\n{afterglow_text}"
                )
            else:
                relevant_memories_text = afterglow_text

        # #526 段階 2: 慣化 sidecar の更新は retrieve 後に呼び出し側で行う
        # (retrieve は read-only を保つ)。store / being_id / tick が揃った
        # ときだけ書き込み、いずれかが欠ければ silent skip。
        if (
            self._episodic_recall_habituation_store is not None
            and being_id is not None
            and current_tick_for_habituation is not None
            and recall_result.candidates
        ):
            try:
                self._episodic_recall_habituation_store.record_recall(
                    being_id,
                    [c.episode.episode_id for c in recall_result.candidates],
                    current_tick_for_habituation,
                )
            except Exception:
                # sidecar 書き込み失敗は recall 自体を止めない (graceful)。
                self._logger.warning(
                    "habituation_store.record_recall failed; recall は完走しました",
                    exc_info=True,
                )

        # #526 段階 3: 想起スロット sidecar の更新も retrieve 後に行う。
        # retrieve 内で apply_slot_policy の結果が ``debug.recall_slot_decision``
        # に乗っているので、それを store に反映する。slot off (= decision None)
        # のときは silent skip。
        slot_decision = recall_result.debug.recall_slot_decision
        if (
            self._episodic_recall_slot_store is not None
            and being_id is not None
            and current_tick_for_habituation is not None
            and slot_decision is not None
        ):
            try:
                self._episodic_recall_slot_store.apply_decision(
                    being_id,
                    slot_decision,
                    current_tick=current_tick_for_habituation,
                    cooldown_ticks=self._episodic_recall_slot_cooldown_ticks,
                )
            except Exception:
                self._logger.warning(
                    "recall_slot_store.apply_decision failed; recall は完走しました",
                    exc_info=True,
                )

        # #526 段階 3 PR-C: afterglow store の更新も retrieve 後に行う。
        # retrieve service が apply_afterglow_policy の結果を
        # ``debug.afterglow_index`` に乗せているので、それを store へ反映する。
        # afterglow off のときは index が None なので silent skip。
        afterglow_index = recall_result.debug.afterglow_index
        if (
            self._afterglow_store is not None
            and being_id is not None
            and afterglow_index is not None
        ):
            try:
                self._afterglow_store.apply_decision(being_id, afterglow_index)
            except Exception:
                self._logger.warning(
                    "afterglow_store.apply_decision failed; recall は完走しました",
                    exc_info=True,
                )

        # Issue #283 後続: recall 結果を trace に残す (Viewer / jq から
        # 「どのエピソードが想起されたか」を後追いできる)。candidates が 0
        # でも「recall を試行したが結果は 0」事実は残しておく価値があるので emit。
        # #526 後続: ``retrieval_debug`` を渡し、cue 設計の post-hoc 解析
        # (axis 別 raw 件数 / union 件数 / source_axes 別件数) を可視化する。
        self._emit_episodic_recall_trace(
            player_id=player_id,
            situation_cues=situation_cues,
            candidates=list(recall_result.candidates),
            relevant_memories_text=relevant_memories_text,
            retrieval_debug=recall_result.debug,
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
            # Phase 3 Step 3d-3: legacy 経路は撤去済。Being 未解決時は
            # `_append_recall_observation` が silent skip する (turn は継続)。
            # 未解決をデバッグ可能にするため、ここで 1 度だけ warning ログを
            # 残す (= 候補ごとには出さず recall buffer 全体への記録試行と
            # して 1 回。silent failure 構造的対処、design_decisions.md #5)。
            if being_id is None and recall_result.candidates:
                self._logger.warning(
                    "episodic_recall_buffer skipped: being_id unresolved "
                    "(player_id=%s, candidates=%d). 再解釈 sidecar は動かないが "
                    "turn は継続する。",
                    player_id.value,
                    len(recall_result.candidates),
                )
            for cand in recall_result.candidates:
                try:
                    observation = EpisodicRecallObservation(
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
                    self._append_recall_observation(being_id, observation)
                except Exception as e:
                    self._logger.warning(
                        "Failed to record episodic recall observation; prompt build continues: %s",
                        e,
                        exc_info=True,
                    )

        # Issue #526 後続: 候補 0 件のときも「受動想起の機構は走ったが何も
        # 浮かばなかった」事実を agent 側で可観測にする。``_episodic_passive_recall``
        # 未注入時は上の早期 return で空文字を返しており、ここには到達しない。
        candidate_count = len(recall_result.candidates)
        if not relevant_memories_text.strip():
            relevant_memories_text = "(受動想起では何も浮かばなかった)"

        return relevant_memories_text, candidate_count

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
        additional_freetexts = _gather_additional_freetexts_for_recall(
            observations, action_results
        )
        encounter_tick = self._resolve_encounter_tick()
        situation_cues = build_situation_episodic_cues(
            runtime_context=ui_context.tool_runtime_context,
            observation_structured=observation_structured,
            latest_action=latest_action,
            observation_prose=observation_prose,
            noun_matcher=self._noun_matcher,
            additional_freetexts=additional_freetexts,
            encounter_memory=self._encounter_memory_for_recall,
            encounter_player_id=player_id,
            encounter_current_tick=encounter_tick,
            encounter_recent_window_ticks=self._encounter_recent_window_ticks,
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

    def _append_recall_observation(
        self,
        being_id: Optional["BeingId"],
        observation: EpisodicRecallObservation,
    ) -> None:
        """recall observation を recall_buffer_store に書く helper。

        Phase 3 Step 3d-3: legacy player_id 経路は撤去済。Being 未解決時は
        silent skip (= prompt 強化の graceful fallback、turn は止めない)。
        ``self._episodic_recall_buffer_store is None`` は呼出側で先に弾く前提。

        ``being_id is None`` 時のデバッグ可視性は、呼出側 ``_run_passive_recall``
        で 1 回の warning ログとして残す (= silent failure 構造的対処)。
        """
        assert self._episodic_recall_buffer_store is not None
        if being_id is None:
            return
        self._episodic_recall_buffer_store.append_by_being(being_id, observation)

    def _resolve_being_id(self, player_id: PlayerId) -> Optional["BeingId"]:
        """Resolver+WorldId 揃いなら ``BeingId`` を返す。

        Phase 3 Step 3d-3: ``DefaultPromptBuilder`` の各 Being keyed 経路
        (memo / journal lookup / recall_buffer append) から共有される helper。
        未注入 or Being 未 provision なら ``None`` を返し、呼出側で
        graceful skip / 生 recall_text への縮退に分岐させる。
        """
        if (
            self._being_attachment_resolver is None
            or self._default_world_id is None
        ):
            return None
        return self._being_attachment_resolver.resolve_being_id(
            self._default_world_id, player_id
        )

    def _fetch_uncompleted_memos(self, player_id: PlayerId) -> list[MemoEntry]:
        """being_id 経路で未完了 memo を引く (Phase 3 Step 3a-3)。

        Resolver/WorldId 未注入か Being 未 provision の場合は空リストを返す
        (= prompt 内 memo セクションが「未完了なし」相当として表示される、
        既存 prompt 構築テストが Resolver なしで動く余地を残す)。

        Phase 3 Step 3d-2 review (#497 MEDIUM-2): being_id 解決は共有 helper
        ``_resolve_being_id`` 経由に統一 (= journal / recall_buffer 経路と同じ
        ロジックで Being を引く)。
        """
        assert self._memo_store is not None
        being_id = self._resolve_being_id(player_id)
        if being_id is None:
            return []
        return self._memo_store.list_uncompleted_by_being(being_id)

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
            entries = self._fetch_uncompleted_memos(player_id)
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
