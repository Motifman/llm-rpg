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

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from ai_rpg_world.application.llm.contracts.interfaces import (
    IActionResultStore,
    IAvailableToolsProvider,
    IContextFormatStrategy,
    ICurrentStateFormatter,
    IRecentEventsFormatter,
    IShortTermMemory,
    ISystemPromptBuilder,
)
from ai_rpg_world.application.llm.services.unified_recent_event_store import (
    UnifiedRecentEventStore,
)
from ai_rpg_world.application.observation.contracts.interfaces import (
    IObservationContextBuffer,
)
from ai_rpg_world.application.world.services.world_query_service import (
    WorldQueryService,
)
from ai_rpg_world.domain.memory.episodic.repository.episodic_recall_buffer_repository import (
    EpisodicRecallBufferRepository,
)
from ai_rpg_world.domain.memory.episodic.repository.episodic_reinterpretation_journal_repository import (
    EpisodicReinterpretationJournalRepository,
)
from ai_rpg_world.domain.memory.memo.repository.memo_repository import MemoRepository
from ai_rpg_world.domain.player.repository.player_profile_repository import (
    PlayerProfileRepository,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

if TYPE_CHECKING:
    from ai_rpg_world.application.being.player_acquaintances import PlayerAcquaintances
    from ai_rpg_world.application.encounter.contracts.interfaces import (
        IEncounterMemory,
    )
    from ai_rpg_world.application.llm.services.afterglow_store import (
        IAfterglowStore,
    )
    from ai_rpg_world.application.llm.services.episodic_memory_link_application_service import (
        EpisodicMemoryLinkApplicationService,
    )
    from ai_rpg_world.application.llm.services.episodic_passive_recall_retrieval import (
        EpisodicPassiveRecallRetrievalService,
    )
    from ai_rpg_world.application.llm.services.episodic_recall_habituation_store import (
        IEpisodicRecallHabituationStore,
    )
    from ai_rpg_world.application.llm.services.episodic_recall_slot_store import (
        IEpisodicRecallSlotStore,
    )
    from ai_rpg_world.application.llm.services.prompt_sections.situation_recall import (
        SituationRecallSources,
    )
    from ai_rpg_world.application.llm.services.semantic_passive_recall_service import (
        SemanticPassiveRecallService,
    )
    from ai_rpg_world.application.llm.services.world_noun_matcher import (
        IWorldNounMatcher,
    )
    from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
    from ai_rpg_world.application.world.contracts.queries import GetPlayerCurrentStateQuery
    from ai_rpg_world.domain.memory.episodic.repository.pending_prediction_repository import (
        PendingPredictionRepository,
    )
    from ai_rpg_world.domain.player.aggregate.player_profile_aggregate import PlayerProfileAggregate


DEFAULT_RECENT_OBSERVATIONS_LIMIT = 20
DEFAULT_RECENT_ACTIONS_LIMIT = 20
DEFAULT_EPISODIC_PASSIVE_RECALL_LIMIT_PER_AXIS = 10
DEFAULT_EPISODIC_PASSIVE_RECALL_MAX_CANDIDATES = 10
DEFAULT_ACTION_INSTRUCTION = "利用可能なツールで次の行動を選んでください。"
DEFAULT_TILE_MAP_VIEW_DISTANCE = 5
DEFAULT_MEMO_STALE_AGE_TICKS = 20


class _PlayerCurrentStateSource(Protocol):
    """prompt 組み立てに要るのは現在状態の取得だけ。"""

    def get_player_current_state(
        self, query: GetPlayerCurrentStateQuery
    ) -> PlayerCurrentStateDto | None: ...


class _PlayerProfileSource(Protocol):
    """prompt 組み立てに要るのは profile の取得だけ。"""

    def find_by_id(self, player_id: PlayerId) -> PlayerProfileAggregate | None: ...


@dataclass(frozen=True)
class PromptBuilderCoreServices:
    """DefaultPromptBuilder が必須とするインフラサービス群。

    全て non-Optional。wiring 側で対応する依存を解決して渡すことを想定する。
    """

    observation_buffer: IObservationContextBuffer
    short_term_memory: IShortTermMemory
    action_result_store: IActionResultStore
    recent_event_store: UnifiedRecentEventStore
    # 本体の service ではなく、必要な 1 メソッドだけを要求する。
    # world_runtime は duck-type adapter を渡す (#1371)。
    world_query_service: _PlayerCurrentStateSource
    player_profile_repository: _PlayerProfileSource
    current_state_formatter: ICurrentStateFormatter
    recent_events_formatter: IRecentEventsFormatter
    context_format_strategy: IContextFormatStrategy
    system_prompt_builder: ISystemPromptBuilder
    available_tools_provider: IAvailableToolsProvider
    recent_events_projection: Callable[[PlayerId, list[Any]], tuple[list[Any], tuple[str, ...]]] | None = None
    observation_repetition_projection: Callable[[list[Any]], list[Any]] | None = None


@dataclass(frozen=True)
class PromptSectionProviders:
    """各 prompt section の任意 provider 群。

    未設定なら該当 section は省略される。world_runtime runtime のような独自の
    objective / inventory section を持つ runtime はこれらを注入する。
    """

    persona_block_provider: Callable[[PlayerId], str] | None = None
    objective_text_provider: Callable[[PlayerId], str] | None = None
    inventory_text_provider: Callable[[PlayerId], str] | None = None
    # #1520: Being が描いた【知っている人】。system prompt ではなく毎ターンの
    # メッセージの、目的の直後に置く。
    known_people_text_provider: Callable[[PlayerId], str] | None = None
    memo_store: MemoRepository | None = None


@dataclass(frozen=True)
class EpisodicRecallConfig:
    """受動想起・記憶リンク・再解釈の Optional 設定。

    Issue #240 で導入された episodic memory 系の一式。passive_recall が None なら
    関連処理ごとスキップされ、prompt に「関連する記憶」section が出ない。
    """

    passive_recall: EpisodicPassiveRecallRetrievalService | None = None
    passive_recall_limit_per_axis: int = DEFAULT_EPISODIC_PASSIVE_RECALL_LIMIT_PER_AXIS
    passive_recall_max_candidates: int = DEFAULT_EPISODIC_PASSIVE_RECALL_MAX_CANDIDATES
    memory_link_service: EpisodicMemoryLinkApplicationService | None = None
    recall_buffer_store: EpisodicRecallBufferRepository | None = None
    reinterpretation_journal_store: EpisodicReinterpretationJournalRepository | None = None
    turn_index_provider: Callable[[PlayerId], int] | None = None
    # Issue #283 後続: 観測 prose に含まれる固有名詞から自動 cue を立てる
    # マッチャ。None なら自由文経路は無効化 (= 構造化フィールドだけが cue 源)。
    # 実装は ``IWorldNounMatcher`` 準拠の任意クラス (Aho-Corasick / Null / C 拡張等)。
    noun_matcher: IWorldNounMatcher | None = None
    # Phase 1c: semantic memory の passive top-K recall。
    # service=None または top_k=0 なら prompt §「【関連する学び】」は出ない。
    # 詳細は docs/memory_system/semantic_memory_activation_plan.md §4。
    semantic_passive_recall: SemanticPassiveRecallService | None = None
    semantic_passive_top_k: int = 0
    # #1414: 渡すと【関連する学び】を状況の項目から引く。件数は semantic_passive_top_k。
    situation_recall: SituationRecallSources | None = None
    # PR8 (R5): Encounter Memory を recall cue trigger として使う。注入時、
    # 直近 ``encounter_recent_window_ticks`` 以内に encounter した entity /
    # spot / event が ``ENCOUNTER`` source の cue として recall に乗る。
    # current_tick 取得は prompt_builder の ``current_tick_provider`` を流用。
    encounter_memory: IEncounterMemory | None = None
    encounter_recent_window_ticks: int = 5
    # encounter の spot key はシナリオの文字列 ID なので、runtime 由来の
    # place_spot cue (数値 spot_id) と揃えるために数値へ直す。
    encounter_spot_id_resolver: Callable[[str], int] | None = None
    # #1520: 直近に会った相手は、環境の encounter ではなく Being の知り合いの
    # 記録から引く。「直近」は Being のターン数で数える。
    acquaintances: PlayerAcquaintances | None = None
    acquaintance_recent_window_turns: int = 5
    # #526 段階 2: 慣化ペナルティの sidecar store。注入時のみ動く
    # (= default off で既存挙動と同一)。retrieve 後に prompt_builder が
    # 採用された episode の last_recalled_tick を記録する。
    recall_habituation_store: IEpisodicRecallHabituationStore | None = None
    recall_habituation_decay_window_ticks: int = 5
    # #526 段階 3: 想起スロット (working memory) の sidecar store と
    # cooldown 設定。注入時のみ動く (= default off で既存挙動と同一)。
    # 4 つのスロット運用パラメータのうち、prompt_builder が apply_decision で
    # 必要なのは ``cooldown_ticks`` のみ (他 3 つは retrieve service 側で保持)。
    recall_slot_store: IEpisodicRecallSlotStore | None = None
    recall_slot_cooldown_ticks: int = 5
    # #526 段階 3 PR-C: afterglow index sidecar (= ぼんやり覚えてる)。
    # 注入時のみ動く (= default off で既存挙動と同一)。retrieve service
    # 側で apply_afterglow_policy の結果が ``debug.afterglow_index`` に乗る
    # ので、prompt_builder は store.apply_decision (書込) と prompt 表示の
    # ために参照する。
    afterglow_store: IAfterglowStore | None = None
    # U10a (予測誤差統一設計 部品6・pending prediction / default off): 抽出
    # された約束・見込みの per-Being store。注入時のみ動く (= default off で
    # 既存挙動と同一)。他の sidecar store (recall_habituation_store 等) と
    # 同じく「store が None なら機構自体が無効」で判定し、別の enabled bool
    # は持たない。
    pending_prediction_store: PendingPredictionRepository | None = None
    # 再浮上の cap (1 ターンに出す件数の上限)。乱発防止のための構造的な歯止め。
    pending_prediction_resurface_cap: int = 2


@dataclass(frozen=True)
class PromptLimits:
    """数値設定・action_instruction・tile_map フラグ。"""

    recent_observations_limit: int = DEFAULT_RECENT_OBSERVATIONS_LIMIT
    recent_actions_limit: int = DEFAULT_RECENT_ACTIONS_LIMIT
    default_action_instruction: str = DEFAULT_ACTION_INSTRUCTION
    tile_map_view_distance: int = DEFAULT_TILE_MAP_VIEW_DISTANCE
    tile_map_enabled: bool = True
    memo_stale_age_ticks: int = DEFAULT_MEMO_STALE_AGE_TICKS
    #: メモの経過を世界の時計の分で書くための換算。None なら手番の回数で書く (#1562)。
    minutes_per_tick: int | None = None
