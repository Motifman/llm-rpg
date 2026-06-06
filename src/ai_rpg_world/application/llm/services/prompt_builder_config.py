"""DefaultPromptBuilder 用の Config dataclass 群。

Issue #227 後続レビュー (HIGH-1) 改善: __init__ の 22 引数を 4 つの dataclass に
グループ化し、テスト fixture や wiring 側の組み立てを楽にする。各 dataclass は
「機能の塊」として独立しており、Optional な機能 (episodic recall, memo, etc.)
は丸ごと省略できる。

API:
    DefaultPromptBuilder(
        core=PromptBuilderCoreServices(...),     # 必須インフラ
        sections=PromptSectionProviders(...),    # オプション section 群
        episodic=EpisodicRecallConfig(...),      # 受動想起・記憶リンク
        limits=PromptLimits(...),                # 数値設定・action_instruction
        ui_context_builder=None,
        current_tick_provider=None,
    )

各 dataclass は frozen で immutable。検証は DefaultPromptBuilder.__init__ で行う。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional, TYPE_CHECKING

from ai_rpg_world.application.llm.contracts.episodic_reinterpretation import (
    IEpisodicRecallBufferStore,
    IEpisodicReinterpretationJournalStore,
)
from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    IAvailableToolsProvider,
    IContextFormatStrategy,
    ICurrentStateFormatter,
    IMemoStore,
    IRecentEventsFormatter,
    ISlidingWindowMemory,
    ISystemPromptBuilder,
)
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
)
from ai_rpg_world.application.world.services.world_query_service import (
    WorldQueryService,
)
from ai_rpg_world.domain.player.repository.player_profile_repository import (
    PlayerProfileRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.services.episodic_memory_link_application_service import (
        EpisodicMemoryLinkApplicationService,
    )
    from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
        EpisodicPassiveRecallRetrievalService,
    )
    from ai_rpg_world.application.llm.services.world_noun_matcher import (
        IWorldNounMatcher,
    )


DEFAULT_RECENT_OBSERVATIONS_LIMIT = 20
DEFAULT_RECENT_ACTIONS_LIMIT = 20
DEFAULT_EPISODIC_PASSIVE_RECALL_LIMIT_PER_AXIS = 10
DEFAULT_EPISODIC_PASSIVE_RECALL_MAX_CANDIDATES = 10
DEFAULT_ACTION_INSTRUCTION = "利用可能なツールで次の行動を選んでください。"
DEFAULT_TILE_MAP_VIEW_DISTANCE = 5
DEFAULT_MEMO_STALE_AGE_TICKS = 20


@dataclass(frozen=True)
class PromptBuilderCoreServices:
    """DefaultPromptBuilder が必須とするインフラサービス群。

    全て non-Optional。wiring 側で対応する依存を解決して渡すことを想定する。
    """

    observation_buffer: IObservationContextBuffer
    sliding_window_memory: ISlidingWindowMemory
    action_result_store: IActionResultStore
    world_query_service: WorldQueryService
    player_profile_repository: PlayerProfileRepository
    current_state_formatter: ICurrentStateFormatter
    recent_events_formatter: IRecentEventsFormatter
    context_format_strategy: IContextFormatStrategy
    system_prompt_builder: ISystemPromptBuilder
    available_tools_provider: IAvailableToolsProvider


@dataclass(frozen=True)
class PromptSectionProviders:
    """各 prompt section の任意 provider 群。

    未設定なら該当 section は省略される。escape_game runtime のような独自の
    objective / inventory section を持つ runtime はこれらを注入する。
    """

    persona_block_provider: Optional[Callable[[PlayerId], str]] = None
    objective_text_provider: Optional[Callable[[PlayerId], str]] = None
    inventory_text_provider: Optional[Callable[[PlayerId], str]] = None
    memo_store: Optional[IMemoStore] = None


@dataclass(frozen=True)
class EpisodicRecallConfig:
    """受動想起・記憶リンク・再解釈の Optional 設定。

    Issue #240 で導入された episodic memory 系の一式。passive_recall が None なら
    関連処理ごとスキップされ、prompt に「関連する記憶」section が出ない。
    """

    passive_recall: Optional["EpisodicPassiveRecallRetrievalService"] = None
    passive_recall_limit_per_axis: int = DEFAULT_EPISODIC_PASSIVE_RECALL_LIMIT_PER_AXIS
    passive_recall_max_candidates: int = DEFAULT_EPISODIC_PASSIVE_RECALL_MAX_CANDIDATES
    memory_link_service: Optional["EpisodicMemoryLinkApplicationService"] = None
    recall_buffer_store: Optional[IEpisodicRecallBufferStore] = None
    reinterpretation_journal_store: Optional[IEpisodicReinterpretationJournalStore] = None
    turn_index_provider: Optional[Callable[[PlayerId], int]] = None
    # Issue #283 後続: 観測 prose に含まれる固有名詞から自動 cue を立てる
    # マッチャ。None なら自由文経路は無効化 (= 構造化フィールドだけが cue 源)。
    # 実装は ``IWorldNounMatcher`` 準拠の任意クラス (Aho-Corasick / Null / C 拡張等)。
    noun_matcher: Optional["IWorldNounMatcher"] = None
    # Phase 1c: semantic memory の passive top-K recall。
    # service=None または top_k=0 なら prompt §「【関連する学び】」は出ない。
    # 詳細は docs/memory_system/semantic_memory_activation_plan.md §4。
    semantic_passive_recall: Optional["SemanticPassiveRecallService"] = None
    semantic_passive_top_k: int = 0


@dataclass(frozen=True)
class PromptLimits:
    """数値設定・action_instruction・tile_map フラグ。"""

    recent_observations_limit: int = DEFAULT_RECENT_OBSERVATIONS_LIMIT
    recent_actions_limit: int = DEFAULT_RECENT_ACTIONS_LIMIT
    default_action_instruction: str = DEFAULT_ACTION_INSTRUCTION
    tile_map_view_distance: int = DEFAULT_TILE_MAP_VIEW_DISTANCE
    tile_map_enabled: bool = True
    memo_stale_age_ticks: int = DEFAULT_MEMO_STALE_AGE_TICKS
