"""LLM エージェントが世界で生きる汎用ランタイム (world_runtime)。

シナリオ JSON → インメモリリポジトリ → アプリケーションサービス をワイヤリングし、
プログラム的にアクションを実行できるようにする。escape ゲーム・survival 等のジャンルに
依存せず、勝敗のない永続世界も含めて同じ turn 実行経路で動かす (経路統一 層1)。

LLM エージェントが**実際に**受け取る観測テキスト・ツール定義・ラベル解決コンテキストを
そのまま可視化する。デモ専用の加工は行わない。
"""

from __future__ import annotations

import logging
import os
import random
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, ClassVar, Dict, FrozenSet, List, Mapping, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


def _new_interaction_cooldown_store():
    """既定の再使用間隔 store。

    module 直下で import すると循環するので、遅延で解決する
    (world_graph 側が world_runtime を参照していないことに依存しない)。
    """
    from ai_rpg_world.application.world_graph.interaction_cooldown_store import (
        InteractionCooldownStore,
    )

    return InteractionCooldownStore()


class ToolExposureConfigurationError(RuntimeError):
    """runtime config が要求する LLM ツールを配線できないときの起動時エラー。"""


from ai_rpg_world.domain.memory.goal.service.stagnation_pressure_band import (
    STAGNATION_PRESSURE_BAND_NONE,
    resolve_stagnation_pressure_band,
)
from ai_rpg_world.domain.item.read_model.item_spec_read_model import ItemSpecReadModel
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    grant_initial_items_to_inventory,
)
from ai_rpg_world.application.player.services.player_life_query import PlayerLifeQuery
from ai_rpg_world.application.player.services.player_outcome_observation_formatter import (
    PlayerOutcomeObservationFormatter,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.player_navigation_state import PlayerNavigationState
from ai_rpg_world.domain.player.value_object.player_spot_navigation_state import PlayerSpotNavigationState
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum
from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import GameEndConditionEvaluator
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.game_end_result import GameEndResult
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.world_flag_registry import WorldFlagRegistry

from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world_graph.spot_exploration_application_service import (
    SpotExplorationApplicationService,
    SpotExplorationResultDto,
)
from ai_rpg_world.application.world_graph.spot_exploration_progress_store import (
    InMemorySpotExplorationProgressStore,
)
from ai_rpg_world.application.world_graph.spot_interaction_application_service import (
    SpotInteractionApplicationService,
    SpotInteractionResultDto,
)
from ai_rpg_world.application.world_graph.spot_graph_day_night_stage_service import (
    SpotGraphDayNightStageService,
)
from ai_rpg_world.application.world_graph.spot_graph_needs_decay_stage_service import (
    SpotGraphNeedsDecayStageService,
)
from ai_rpg_world.application.trade.services.in_memory_market_board_store import (
    InMemoryMarketBoardStore,
)
from ai_rpg_world.domain.trade.value_object.market_reach import (
    MarketReach,
)
from ai_rpg_world.application.trade.services.market_service import MarketService
from ai_rpg_world.application.world_graph.overflow_sinks import (
    GroundOverflowSink,
    refuse_overflow,
)
from ai_rpg_world.application.trade.services.in_memory_pending_trade_offer_store import (
    InMemoryPendingTradeOfferStore,
)
from ai_rpg_world.application.trade.services.player_trade_service import (
    PlayerTradeService,
)
from ai_rpg_world.application.trade.services.trade_freeze_service import (
    TradeFreezeService,
)
from ai_rpg_world.application.trade.services.market_order_expiry_stage import (
    MarketOrderExpiryStage,
)
from ai_rpg_world.application.trade.services.trade_offer_expiry_stage import (
    TradeOfferExpiryStage,
)
from ai_rpg_world.application.world_graph.spot_graph_merchant_trade_service import (
    SpotGraphMerchantTradeService,
)
from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
    SpotGraphItemTransferService,
    ItemTransferResult,
)
from ai_rpg_world.application.world_graph.spot_graph_movement_application_service import (
    SpotGraphMovementApplicationService,
)
from ai_rpg_world.application.world_graph.spot_graph_environment_stage_service import (
    SpotGraphEnvironmentStageService,
)
from ai_rpg_world.application.world_graph.spot_graph_scenario_event_progress_store import (
    InMemorySpotGraphScenarioEventProgressStore,
)
from ai_rpg_world.application.world_graph.reactive_object_state_binding_stage_service import (
    ReactiveObjectStateBindingStageService,
)
from ai_rpg_world.application.world_graph.reactive_passage_binding_stage_service import (
    ReactivePassageBindingStageService,
)
from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.application.world_graph.scenario_predicate_trace_emitter import (
    ScenarioPredicateTraceEmitter,
)
from ai_rpg_world.application.world_graph.synchronized_action_registry import (
    SynchronizedActionRegistry,
)
from ai_rpg_world.application.world_graph.synchronized_action_resolver_stage_service import (
    SynchronizedActionResolverStageService,
)
from ai_rpg_world.application.world_graph.spot_graph_scenario_event_stage_service import (
    SpotGraphScenarioEventStageService,
)
from ai_rpg_world.application.llm.contracts.interfaces import ILlmTurnTrigger
from ai_rpg_world.application.world_graph.spot_graph_simulation_application_service import (
    SpotGraphSimulationApplicationService,
)
from ai_rpg_world.application.world_graph.spot_graph_travel_context import (
    SpotGraphTravelContextProvider,
)
from ai_rpg_world.application.world_graph.spot_graph_travel_stage_service import (
    SpotGraphTravelStageService,
)
from ai_rpg_world.application.world_graph.world_flag_state import (
    MutableWorldFlagState,
    WorldFlagChange,
    WorldFlagMutationContext,
    WorldFlagMutationSource,
)
from ai_rpg_world.application.world_graph.game_phase_store import GamePhaseStore
from ai_rpg_world.application.world_graph.meeting_command_service import (
    MeetingCommandService,
    MeetingOngoingCondition,
)
from ai_rpg_world.application.world_graph.spot_graph_current_state_builder import (
    SpotGraphCurrentStateBuilder,
)
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphInventoryItemEntry,
)
from ai_rpg_world.application.world_graph.distant_view_service import (
    DistantViewArea,
    DistantViewCandidate,
    DistantViewConnection,
    DistantViewService,
    DistantViewSpot,
    DistantViewVisibleCandidate,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    collect_owned_item_spec_ids_from_inventory,
)

from ai_rpg_world.application.llm.services.spot_graph_current_state_formatter import (
    SpotGraphCurrentStateFormatter,
)
from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    SpotGraphUiContextBuilder,
)
from ai_rpg_world.application.llm.services.prompt_argument_contract import (
    PromptArgumentContractError,
    PromptArgumentContractViolation,
    find_prompt_argument_contract_violations,
)
from ai_rpg_world.application.llm.services.action_summary_format import (
    project_action_arguments_for_history,
)
from ai_rpg_world.application.llm.contracts.action_argument_classification import (
    ActionArgumentClassificationError,
    unclassified_action_argument_names,
)
from ai_rpg_world.application.llm.contracts.dtos import (
    LlmCommandResultDto,
    LlmUiContextDto,
    ToolDefinitionDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.being.acting_being import ActingBeing
from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import get_spot_graph_specs
from ai_rpg_world.application.llm.services.tool_catalog.subjective_action import (
    assess_situation_definition,
    strip_reason_first_action_subjective_schema,
    with_expected_result_schema,
    GOAL_OUTCOME_ABANDONED,
    GOAL_OUTCOME_ACHIEVED,
    with_goal_outcome_schema,
    with_goal_update_schema,
)
from ai_rpg_world.application.llm.tool_exposure import ToolExposure
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_MEMORY_EXPLORE_RELATED,
    TOOL_NAME_MEMORY_RECALL_EPISODES,
    TOOL_NAME_MEMORY_SEARCH_SEMANTIC,
    TOOL_NAME_SPEECH,
    TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_LISTEN,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
    TOOL_NAME_SPOT_GRAPH_PREPARE_ACTION,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)
from ai_rpg_world.application.llm.services.tool_catalog.memory import get_memory_specs
from ai_rpg_world.application.llm.services.sliding_window_memory import DefaultSlidingWindowMemory
from ai_rpg_world.application.llm.contracts.interfaces import IShortTermMemory
from ai_rpg_world.application.llm.services.action_result_store import DefaultActionResultStore
from ai_rpg_world.application.llm.services.unified_recent_event_store import (
    UnifiedRecentEventStore,
)
from ai_rpg_world.application.llm.services.action_result_recorder import ActionResultRecorder
from ai_rpg_world.application.llm.services.prediction_context_ledger import (
    PredictionContextLedger,
)
from ai_rpg_world.application.llm.services.context_format_strategy import (
    SectionBasedContextFormatStrategy,
)
from ai_rpg_world.application.llm.services.recent_events_formatter import DefaultRecentEventsFormatter
from ai_rpg_world.application.llm.services.in_memory_todo_store import InMemoryTodoStore
from ai_rpg_world.application.llm.services.executors.todo_executor import TodoToolExecutor
from ai_rpg_world.application.llm.services.world_llm_prompt import (
    CharacterPromptInput,
    build_world_system_prompt,
    build_persona_block_from_character,
    safe_world_intro_text,
)
from ai_rpg_world.application.llm.services.world_briefing import (
    build_recorded_player_state_tick_keys,
    build_own_state_display_names,
    build_world_briefing,
)
from ai_rpg_world.application.encounter.in_memory_encounter_memory import (
    InMemoryEncounterMemory,
)
from ai_rpg_world.application.encounter.services.encounter_observation_collector import (
    EncounterObservationCollector,
)
from ai_rpg_world.domain.memory.encounter.value_object.encounter_key import (
    EncounterKey,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry, ObservationOutput
from ai_rpg_world.application.observation.services.heartbeat_observation_emitter import (
    HeartbeatObservationEmitter,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import DefaultObservationContextBuffer
from ai_rpg_world.application.observation.services.observation_pipeline import ObservationPipeline
from ai_rpg_world.application.observation.services.observation_formatter import ObservationFormatter
from ai_rpg_world.application.observation.services.observation_appender import (
    ObservationAppender,
)
from ai_rpg_world.application.observation.services.observation_recipient_resolver import (
    create_observation_recipient_resolver,
)
from ai_rpg_world.application.observation.services.observation_turn_scheduler import (
    ObservationTurnScheduler,
)
from ai_rpg_world.application.speech.contracts.commands import SpeakCommand
from ai_rpg_world.application.speech.services.player_speech_service import (
    PlayerSpeechApplicationService,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.world_runtime.pipeline_event_publisher import PipelineEventPublisher
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel

from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import InMemoryItemRepository
from ai_rpg_world.infrastructure.repository.in_memory_monster_aggregate_repository import (
    InMemoryMonsterAggregateRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_monster_template_repository import (
    InMemoryMonsterTemplateRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_skill_loadout_repository import (
    InMemorySkillLoadoutRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_item_spec_repository import InMemoryItemSpecRepository
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import InMemoryPlayerInventoryRepository
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import InMemoryPlayerStatusRepository
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import InMemorySpotGraphRepository
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import InMemorySpotInteriorRepository

from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    ScenarioLoadResult,
    ScenarioLoader,
    ScenarioMetadata,
    PlayerSpawnConfig,
)
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMapper
from ai_rpg_world.domain.world_graph.value_object.scenario_event_def import ScenarioEventDef
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
    InMemoryGameTimeProvider,
)
from ai_rpg_world.domain.world_graph.enum.meeting_trigger import (
    MeetingEndReason,
    MeetingStartTrigger,
)


class WorldStandaloneNoopLlmTurnTrigger(ILlmTurnTrigger):
    """単体 `create_world_runtime` 用の ILlmTurnTrigger 実装。

    当ファクトリは LLM オーケストラを内蔵しない。ティック後フック
    :class:`SpotGraphSimulationApplicationService` 契約を満たすためのプレースホルダ。
    プレゼンテーション層のセッション生成後は
    :meth:`WorldRuntime.set_simulation_llm_turn_trigger` で本物の
    トリガ（例: セッションの ``_WorldLlmTurnTrigger``）に差し替える。
    """

    def schedule_turn(self, player_id: PlayerId) -> None:  # noqa: ARG002
        return None

    def run_scheduled_turns(self) -> None:
        return None


def _other_explorer_names_for_world_system_prompt(
    spawns: Tuple[PlayerSpawnConfig, ...],
    world_character: Optional[CharacterPromptInput],
) -> tuple[str, ...]:
    """【同じ局面にいる者】用の表示名。自身（LLM ペルソナ）に対応するスポーンは含めない。

    シナリオ上の他プレイヤー全員名ではなく、同席する他者のみ述べるため、単体プレイでは空になる。
    `world_character` 未指定時は `player_spawns[0]` を操作対象（ペルソナのフォールバック名と同じ扱い）とみなし除外する。
    """
    if not spawns:
        return ()
    self_spawn: Optional[PlayerSpawnConfig] = None
    if world_character is not None:
        cid = (world_character.character_id or "").strip()
        if cid:
            for s in spawns:
                if s.string_id == cid:
                    self_spawn = s
                    break
        if self_spawn is None:
            cname = (world_character.name or "").strip()
            if cname:
                for s in spawns:
                    if s.name == cname:
                        self_spawn = s
                        break
    if self_spawn is None:
        self_spawn = spawns[0]
    return tuple(s.name for s in spawns if s is not self_spawn)


#: 昼夜サイクルを宣言していない世界の 1 tick あたりの分数。
#:
#: ``_time_label`` の後方互換フォールバックと同じ値。**別々に持つと、地図の
#: 「5 分」と時計の進み方が静かにずれる。**
_FALLBACK_MINUTES_PER_TICK = 5

#: 「まもなく打ち切られる」に切り替える残り tick。
#:
#: 最後の 1 tick では遅い。移動も相談もできないまま終わる。2 tick あれば
#: 「誰に入れるか」を一度やり取りできる。
_MEETING_URGENT_REMAINING_TICKS = 2


def _minutes_per_tick(scenario) -> Optional[int]:
    """1 tick が世界の時計で何分か。

    現在時刻の表示 (`深夜 0:05`) と同じ換算を使う。エージェントはその時計を
    毎ターン見ているので、**同じ単位で書けばアリバイの検算がそのままできる**。

    昼夜サイクルを宣言していない世界は ``_time_label`` と同じ 5 分/tick に
    倒す。時計だけ進んで地図が別単位、という食い違いを作らない。
    """
    day_night = getattr(scenario, "day_night_config", None)
    ticks_per_day = getattr(day_night, "ticks_per_day", None) if day_night else None
    if isinstance(ticks_per_day, int) and ticks_per_day > 0:
        return (24 * 60) // ticks_per_day
    return _FALLBACK_MINUTES_PER_TICK


def _required_task_count(scenario) -> Optional[int]:
    """勝利条件が要求する点検の数。宣言が無ければ None。

    **手書きの数字と食い違わせないため、勝ち筋もデータから読む。**
    """
    for condition in getattr(scenario, "win_conditions", ()) or ():
        count = getattr(condition, "min_set_count", None)
        if isinstance(count, int) and not isinstance(count, bool):
            return count
    return None


def _scenario_has_goal(scenario: ScenarioLoadResult) -> bool:
    """勝敗条件を宣言するシナリオか (= goal あり) を導出する (#526 U5, P5)。

    win/lose/end/player outcome 規則のいずれかがあれば goal 前提の文面・目的層
    locked=True。
    既存シナリオは全て game_end_conditions を持つので True になり、system
    prompt / goal seed の挙動は不変。

    個人結果規則を持つ島シナリオも含めるのが必須。win/lose 配列だけを見ると
    「勝敗条件なしの open world」に誤判定され、目的が unlocked (=
    goal_update で書き換え・清算できる) になってしまう。

    ``build_world_system_prompt`` の safe_intro 判定 (create_world_runtime) と
    goal 目的層の seed 判定 (WorldRuntime._resolve_objective_via_goal_store)
    の両方がこの 1 つの導出ロジックを共有する (判定基準の分岐を防ぐ)。
    """
    return bool(
        scenario.win_conditions
        or scenario.lose_conditions
        or scenario.end_conditions
        or scenario.player_outcome_rules
    )


#: `disabled_tools` では落とせないが、**実験設定で落とせる**ツール。
#:
#: この分け方には理由がある。ここに並ぶツールは「世界に在るか」ではなく
#: **「この実験で使うか」**で決まる (同じシナリオを profile 違いで回すときに
#: 変わるのはこちら)。だから宣言の場所がシナリオではない。
#:
#: ただし**止めるだけでは足りない**。「指定できるのは …」だけを返すと、書いた人は
#: 「この世界では落とせない」と読む。実際は落とせて、場所が違うだけ。
#: **行き先の無い拒否は、拒否された側に推測を強いる。**
_TURNED_OFF_BY_EXPERIMENT_CONFIG = {
    "memo_add": "MEMO_TOOLS_ENABLED",
    "memo_list": "MEMO_TOOLS_ENABLED",
    "memo_done": "MEMO_TOOLS_ENABLED",
    "memory_recall_episodes": "EPISODIC_RECALL_ENABLED",
    "memory_recall_by_handle": "EPISODIC_RECALL_ENABLED",
    "memory_explore_related": "EPISODIC_EXPLORE_RELATED_ENABLED",
    "memory_search_semantic": "SEMANTIC_SEARCH_ENABLED",
}


def _where_to_turn_off_instead(unknown) -> str:
    """実験設定で落とせる名前が混ざっていたら、その行き先を添える。"""
    elsewhere = {
        name: _TURNED_OFF_BY_EXPERIMENT_CONFIG[name]
        for name in unknown
        if name in _TURNED_OFF_BY_EXPERIMENT_CONFIG
    }
    if not elsewhere:
        return ""
    where = ", ".join(
        f"{name} は実験設定の {flag}=0" for name, flag in sorted(elsewhere.items())
    )
    return (
        f" / なお、これらはシナリオではなく実験設定で落とします: {where}"
        " (profile または EXPERIMENT_CONFIG に書く)"
    )


@dataclass
class WorldRuntime:
    """LLM エージェントが世界で生きる汎用ランタイム（全てインメモリ）。"""

    scenario: ScenarioLoadResult
    _spot_graph_repo: InMemorySpotGraphRepository
    _spot_interior_repo: InMemorySpotInteriorRepository
    _player_status_repo: InMemoryPlayerStatusRepository
    _player_life_query: PlayerLifeQuery
    _player_perception_policy: "PlayerPerceptionPolicy"
    _fallen_body_registry: "FallenBodyRegistry"
    _departed_position_store: "DepartedPositionStore"
    _player_inventory_repo: InMemoryPlayerInventoryRepository
    _item_repo: InMemoryItemRepository
    _item_spec_repo: InMemoryItemSpecRepository
    _world_flag_state: MutableWorldFlagState
    _effect_service: "WorldGraphEffectService"
    _exploration_progress: InMemorySpotExplorationProgressStore
    _movement_service: SpotGraphMovementApplicationService
    _interaction_service: SpotInteractionApplicationService
    _player_interaction_service: "PlayerInteractionApplicationService"
    _exploration_service: SpotExplorationApplicationService
    _item_transfer_service: SpotGraphItemTransferService
    # 経済統合 Phase 1: 同席する NPC 商人との売買。商人を宣言しない世界では
    # merchants が空のまま作られ、どの売買も「商人が居ない」で落ちる。
    _merchant_trade_service: SpotGraphMerchantTradeService
    # 経済統合 Phase 2: 返事待ちの取引提案。宣言の無い世界では空のまま使われ
    # ない。提案は二人の間にある状態なので world snapshot 側に載る。
    _pending_trade_offer_store: InMemoryPendingTradeOfferStore
    # 経済統合 Phase 2: 提案に出したものを、返事がつくまで使えなくする。
    _trade_freeze_service: TradeFreezeService
    _player_trade_service: PlayerTradeService
    # 経済統合 Phase 3: 掲示板型の市場。板は世界の状態なので world snapshot
    # 側に載る。宣言の無い世界では板が空のまま使われない。
    _market_board_store: InMemoryMarketBoardStore
    _market_service: MarketService
    # 持ちきれなかった品の行き先 (足元へ落とす)。観測の publisher を
    # 後付けするために runtime が持つ。
    _ground_overflow_sink: Any
    _state_builder: SpotGraphCurrentStateBuilder
    _game_end_evaluator: GameEndConditionEvaluator
    _formatter: SpotGraphCurrentStateFormatter
    _ui_context_builder: SpotGraphUiContextBuilder
    _obs_pipeline: ObservationPipeline
    _obs_buffer: DefaultObservationContextBuffer
    _recent_event_store: UnifiedRecentEventStore
    _short_term_memory: IShortTermMemory
    _action_result_store: DefaultActionResultStore
    # PR3 (Encounter Memory): familiarity 信号 (初対面 / 再会 / 初訪問 / 再訪)
    # を保持する。observation pipeline 経由で entity / event の encounter を記録、
    # snapshot codec で永続化される。factory function が必ず生成して渡す
    # (= default なし、既存の memory subsystem と同列の扱い)。
    _encounter_memory: InMemoryEncounterMemory
    _time_provider: InMemoryGameTimeProvider
    _simulation_service: SpotGraphSimulationApplicationService
    _scenario_event_stage: SpotGraphScenarioEventStageService
    _scenario_event_progress: InMemorySpotGraphScenarioEventProgressStore
    # Issue #1046: scenario event / reactive binding / player outcome rule が共有する
    # 確率条件用の乱数源。world snapshot が同じ instance の位置を復元する。
    _scenario_predicate_random: random.Random
    _environment_stage: SpotGraphEnvironmentStageService
    _current_weather: Any
    # 昼夜サイクル stage (Phase B-1)。シナリオに day_night_config が無ければ None。
    _day_night_stage: Optional[SpotGraphDayNightStageService] = field(default=None, repr=False)
    # #344 配線漏れ修正: spot_graph_use_item / attack / give_item / pickup_item /
    # drop_item / prepare_action を experiment runtime 経路で動かすため、
    # ToolExecutor が必要とする monster_repo と attack_orchestrator も runtime に
    # 保持する (factory function が代入する)。monster が居ないシナリオでは None。
    _monster_repo: Any = field(default=None, repr=False)
    _attack_orchestrator: Any = field(default=None, repr=False)
    # Phase E-3: プレイヤー個別 outcome の registry (PlayerId → PlayerOutcomeEnum)。
    # factory は PlayerLifeQuery と同じ instance を構築時に渡す。
    _player_outcome_registry: Optional[Any] = field(default=None, repr=False)
    _tick: int = 0
    # #375 後続: 食料腐敗の日次集約バッファ (code-review HIGH 指摘)。
    # hasattr ベースの遅延初期化だと IDE/mypy / pickle で扱いにくいので
    # dataclass field として明示宣言する。
    # key: spec_id → {"spec_id", "spec_name", "instance_ids": [...]}
    _pending_spoiled: Dict[int, Dict[str, Any]] = field(default_factory=dict, repr=False)
    # 現在 buffer に積まれている食料が属する day (= tick // ticks_per_day)。
    # None は「buffer 空 + 1 件もまだ来ていない」。
    _pending_spoiled_day: Optional[int] = field(default=None, repr=False)
    # 段階3: 動的遠景 cue の false→true 境界検出状態。
    # per-world の事実なので player ごとではなく runtime に保持し、snapshot
    # で保存する。値は {"active": bool, "initialized": bool,
    # "last_changed_tick": int | None}。
    _distant_cue_states: Dict[str, Dict[str, Any]] = field(
        default_factory=dict, repr=False
    )
    # 世界のフェーズ (自由時間 / 会議)。per-world。会議・投票の土台
    # (docs/memory_system/meeting_and_voting_design.md §2.1)。
    # 常にちょうど 1 つのフェーズを持ち、排他は store の遷移メソッドが守る。
    _game_phase_store: "GamePhaseStore" = field(
        default_factory=lambda: GamePhaseStore(), repr=False
    )
    # 対人行為の再使用間隔。per-world。tick 基準で PlayerId をキーにするので
    # Being ではなく world snapshot に載る (codec を同じ PR で入れてある)。
    _interaction_cooldown_store: "InteractionCooldownStore" = field(
        default_factory=lambda: _new_interaction_cooldown_store(), repr=False
    )
    # 会議機構を使うシナリオか (scenario の `meeting` block 由来)。
    # False なら招集・投票の tool を出さず、runtime のメソッドも拒否する。
    # 宣言していない世界のプロンプトを 1 バイトも変えないための切り分け。
    _meeting_enabled: bool = field(default=False, repr=False)
    _meeting_command_service: Optional[MeetingCommandService] = field(
        default=None,
        repr=False,
    )
    # LLM 脱出用（セッション単位で構築）
    # _world_llm_system_prompt: 全プレイヤー共通の system prompt (legacy / 単体プレイ用)
    # _world_llm_system_prompts_by_player_id: Issue #264 第16回実験で発見された
    # 「player 2 (リン) が「リン、〜」と自分名で speech する自呼び回帰」を解消するため、
    # シナリオに複数 player_spawns がある場合は player ごとに persona を埋めた system
    # prompt を持つ。dict が空 / 該当 id 無しなら _world_llm_system_prompt にフォールバック。
    _world_llm_system_prompt: str = field(default="", repr=False)
    _world_llm_system_prompts_by_player_id: Dict[int, str] = field(
        default_factory=dict, repr=False
    )
    _todo_store: InMemoryTodoStore = field(default_factory=InMemoryTodoStore, repr=False)
    _todo_tool_executor: Optional[TodoToolExecutor] = field(default=None, repr=False)
    # U5 (MEMO_DISTILL): memo_done → BeliefEvidence 転記の transcriber。
    # ``_todo_tool_executor`` は ``set_trace_recorder`` 等で作り直される
    # (lazy 再構築) ため、transcriber を setter で 1 度差し込むだけだと
    # 作り直しで静かに失われる (実験 run で MEMO_DISTILL evidence が 0 件に
    # なる silent failure の原因)。runtime 側に保持し、``_wire_auxiliary_tool_stack``
    # が executor を作り直すたびに再適用する。型は circular import 回避で Any。
    _memo_distill_transcriber: Optional[Any] = field(default=None, repr=False)
    # P5 (目的層): GOAL_STORE_ENABLED ON のときだけ構築される goal journal store。
    # OFF なら None (【現在の目的】は従来の静的シナリオ文字列で描画)。
    # 実験 snapshot stub (_wiring_stub_from_world_runtime) がここから拾う。
    _goal_journal_store: Optional[Any] = field(default=None, repr=False)
    # P-U2 (停滞感 store): reflect verdict の畳み込み先カウンタ store。
    # 実験 snapshot stub (_wiring_stub_from_world_runtime) がここから拾う。
    _stagnation_pressure_store: Optional[Any] = field(default=None, repr=False)
    # 案A (band-gated thinking): 停滞 reflect 注入 → 次行動での熟考を橋渡しする
    # 一発ラッチ。transient (session 内制御信号) なので snapshot 非対象。
    _stagnation_reasoning_latch: Optional[Any] = field(default=None, repr=False)
    # reason-first 2段階 turn の有効化。True でも常時 2 段階ではなく、
    # presentation runtime_manager の Phase A 入口で既存 shared state を読んで
    # gated 発火する。下流 execution / episode / prediction 経路は mode 非分岐。
    reason_first_two_step_enabled: bool = field(default=False, repr=False)
    # P6 (目的の見直し): GOAL_REVISION_ENABLED の解決結果と、goal_update を
    # 反映する applier。flag OFF / goal store 無しなら applier は None。
    _goal_revision_enabled: bool = field(default=False, repr=False)
    _goal_revision_applier: Optional[Any] = field(default=None, repr=False)
    # H-1 (伝聞の入力衛生 / 横断レビュー): HEARSAY_ENABLED を
    # BELIEF_EVIDENCE_ENABLED と畳み込んだ実効値。GOAL_REVISION と同じ理由で
    # runtime に保持する (config ミス時に「実際に何が有効か」を後から読める
    # ようにする)。
    _hearsay_enabled: bool = field(default=False, repr=False)
    # Issue #526 後続: LLM が「思い出そう」と意志して過去 episode を呼び戻す
    # ``memory_recall_episodes`` tool の executor。``_wire_auxiliary_tool_stack``
    # 時に episodic_stack が wire されていれば構築。OFF (= 構築されない) なら
    # tool 定義もリストに出さず、run_llm_auxiliary_tool でも未対応扱い。
    # 型は ``Optional["EpisodicMemoryRecallToolExecutor"]`` だが circular import
    # 回避のため lazy import + ``Any`` 注釈にしている (= 既存の lazy executor
    # 配線と同じパターン)。
    _memory_recall_tool_executor: Optional[Any] = field(default=None, repr=False)
    # 能動的にリンク済みエピソードを辿る ``memory_explore_related`` tool の
    # executor。``EPISODIC_EXPLORE_RELATED_ENABLED`` が true かつ link store
    # 一式が組めるときだけ LLM に露出する。
    _memory_explore_related_tool_executor: Optional[Any] = field(
        default=None, repr=False
    )
    # semantic 記憶を能動検索する ``memory_search_semantic`` tool の executor。
    # ``SEMANTIC_SEARCH_ENABLED`` が true かつ semantic store が組めるときだけ
    # LLM に露出する。
    _semantic_memory_search_tool_executor: Optional[Any] = field(
        default=None, repr=False
    )
    # PR-D: afterglow handle から本文を引き戻す ``memory_recall_by_handle``
    # tool の executor。slot / afterglow / episode_store + 現 tick provider を
    # 統合する必要があるため、``_wire_auxiliary_tool_stack`` で構築。
    # 構築されなければ tool 定義もリストに出さず、handler も未対応扱い。
    _memory_recall_by_handle_tool_executor: Optional[Any] = field(default=None, repr=False)
    # シナリオ実行 trace の recorder。未設定なら NullTraceRecorder にフォールバック
    # (Phase 1d 配線)。
    _trace_recorder: Any = field(default=None, repr=False)
    # trace 用の run 内集計。世界状態ではなく観測値なので snapshot へは載せない。
    _cumulative_travel_ticks_by_player: Dict[int, int] = field(
        default_factory=dict, repr=False
    )
    _cumulative_meeting_ticks: int = field(default=0, repr=False)
    # B-4: LLM に提示するツールセットの mode。``True`` (既定) なら TODO 系も
    # 含む従来構成、``False`` なら純スポットグラフ + speech のみ。
    # Issue #155 (TODO 設計の再評価) の判断材料を取るための比較実験用。
    _include_todo_tools: bool = field(default=True, repr=False)
    # Prediction (#526 v0): 行動前の予測 expected_result を core action tool の
    # schema に露出する policy。``"off"`` (露出せず=既定/挙動不変) | ``"optional"``
    # (schema に出すが必須にしない) | ``"required"`` (毎ターン必須)。factory が
    # ResolvedLlmRuntimeConfig.expected_result_policy から設定する。
    _expected_result_policy: str = field(default="off", repr=False)
    # 実験設定の解決済み DTO。遅延構築される component も env を読み直さず、
    # runtime 作成時と同じ設定を見るために保持する。
    _runtime_config: Optional[Any] = field(default=None, repr=False)
    # PR 2 (#227): speech 配信経路統一。PlayerSpokeEvent をドメインイベント
    # として fire し、ObservationPipeline → buffer 経路で配信する。直接
    # broadcast (旧 _append_agent_speech) は廃止。
    _speech_service: Optional[PlayerSpeechApplicationService] = field(
        default=None, repr=False
    )
    _speech_event_publisher: Optional[PipelineEventPublisher] = field(
        default=None, repr=False
    )
    _observation_appender: Optional[ObservationAppender] = field(default=None, repr=False)
    # turn_scheduler はセッション作成時に create_session で注入される
    # (LlmTurnTrigger と llm_player_resolver は wiring で組み立てる必要があるため)
    _observation_turn_scheduler: Optional[ObservationTurnScheduler] = field(
        default=None, repr=False
    )
    # Issue #283 後続: episodic memory pipeline (on/off)。
    # - ``_episodic_stack`` が None なら従来動作 (memory なし)
    # - 注入されていれば ``_record_action_result`` で chunk が積まれ、
    #   prompt builder の recall section に過去エピソードが現れる
    _episodic_stack: Optional[Any] = field(default=None, repr=False)
    # #404 fix: travel_stage を runtime に保持する。create_session 経路から
    # 「到着時の schedule_turn コールバック」を後付けで注入するため、参照を
    # 露出させる必要がある (simulation_service の中に隠れたままだと外から
    # 触れない)。
    _travel_stage: Optional[SpotGraphTravelStageService] = field(default=None, repr=False)
    # #404 P2 (progress 可観測性): driver iteration 内で発火した LLM 呼び出し回数を
    # 集計する単純カウンタ。``_LlmMetricsTraceSink.record`` が bump し、experiment
    # progress reporter が iteration 終端で snapshot + reset する。Phase A の
    # ThreadPoolExecutor で並行 increment され得るため Lock で保護する。
    _llm_call_count: int = field(default=0, repr=False)
    _llm_call_count_lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False
    )

    @property
    def id_mapper(self) -> ScenarioIdMapper:
        return self.scenario.id_mapper

    @property
    def metadata(self) -> ScenarioMetadata:
        return self.scenario.metadata

    def get_player_ids(self) -> List[PlayerId]:
        return [PlayerId(p.player_id) for p in self.scenario.player_spawns]

    def get_player_name(self, player_id: PlayerId) -> str:
        for p in self.scenario.player_spawns:
            if p.player_id == int(player_id):
                return p.name
        return f"Player-{int(player_id)}"

    def current_tick(self) -> int:
        return self._time_provider.get_current_tick().value

    def bump_llm_call_count(self) -> None:
        """LLM 呼び出し 1 件分カウンタを進める (#404 P2)。

        ``_LlmMetricsTraceSink.record`` から呼ばれる thread-safe な counter。
        並列 Phase A の hot path に乗るので、失敗してログを濁さないために
        Lock 取得失敗時は黙って諦める設計には **しない** (Lock 取得は確実に
        成功する想定。bump 失敗 = メトリクス欠損 = silent failure)。
        """
        with self._llm_call_count_lock:
            self._llm_call_count += 1

    def pop_llm_call_count(self) -> int:
        """累積カウンタを返してリセットする。

        experiment progress reporter が 1 driver iteration の終端で呼ぶ想定。
        increment との race を防ぐため Lock 内で read-and-reset を 1 操作にする。
        """
        with self._llm_call_count_lock:
            n = self._llm_call_count
            self._llm_call_count = 0
            return n

    def count_traveling_players(self) -> int:
        """現在 ``is_traveling=True`` の player 数を返す (#404 P2)。

        progress.jsonl の ``travel_active`` フィールド向け。失敗時は 0
        (= 計測欠損) を返す: 進捗集計が status repo の障害で全体停止しない
        ようにする fail-safe。
        """
        try:
            count = 0
            for status in self._player_status_repo.find_all():
                nav = status.spot_navigation_state
                if nav is not None and nav.is_traveling:
                    count += 1
            return count
        except Exception:
            return 0

    def advance_until_player_idle(
        self, player_id: PlayerId, max_ticks: int = 500
    ) -> int:
        """テスト / デモ用ヘルパ: 指定 player の travel が終わるまで tick を進める。

        #404 修正後の ``do_move`` は travel 開始だけして即 return する非同期
        セマンティクスになった。テスト / デモのうち「move したら着いている」
        前提のコードはこのヘルパで後段の tick advance を明示する。

        Args:
            player_id: 待機対象。
            max_ticks: 無限ループ防止の上限 (到達不能や travel state が永遠に
                       立ち続けるバグを test で検知できる安全弁)。
        Returns:
            進めた tick 数。最大に達した場合は max_ticks。
        Raises:
            RuntimeError: max_ticks 内に travel が終わらなかった場合。
        """
        advanced = 0
        for _ in range(max_ticks):
            status = self._player_status_repo.find_by_id(player_id)
            nav = status.spot_navigation_state if status is not None else None
            if nav is None or not nav.is_traveling:
                return advanced
            self.advance_tick()
            advanced += 1
        raise RuntimeError(
            f"advance_until_player_idle: player {player_id.value} が "
            f"{max_ticks} tick 経っても is_traveling のままです (travel state リーク?)"
        )

    def advance_tick(self) -> int:
        try:
            tick = self._simulation_service.tick()
        finally:
            # world tick は stage 失敗時も消費される。残り時間表示と終了判定が
            # time provider から分裂しないよう、成功・失敗の両経路で同期する。
            self._tick = self._time_provider.get_current_tick().value
        # #356 後続: 日が変わったら腐敗バッファを flush して 1 件にまとめる。
        # buffer は _append_food_spoiled_batch_observation で積まれる。
        # tick が 0 base なので day = tick // ticks_per_day。
        pending_day = getattr(self, "_pending_spoiled_day", None)
        if pending_day is not None:
            ticks_per_day = self._ticks_per_day_or_default()
            current_day = tick.value // max(1, ticks_per_day)
            if pending_day != current_day:
                self._flush_pending_food_spoiled()
        self._maybe_close_meeting_on_timeout(tick.value)
        self._record_world_spatial_metrics(tick.value)
        return tick.value

    def _record_committed_player_travel_tick(self, player_id: PlayerId) -> None:
        """確定済みの player 移動 1 tick を実験指標へ反映する。"""
        player_id_value = int(player_id)
        self._cumulative_travel_ticks_by_player[player_id_value] = (
            self._cumulative_travel_ticks_by_player.get(player_id_value, 0) + 1
        )

    def _record_world_spatial_metrics(self, tick: int) -> None:
        """全区画の在室数と各人の累積移動 tick を一つの trace に残す。"""
        recorder = self._trace_recorder
        if recorder is None:
            return
        from ai_rpg_world.application.world_graph.spot_occupancy import (
            SpotOccupancyScope,
            collect_spot_occupancy,
        )

        occupancy = [
            {
                "spot_id": entry.spot_id,
                "spot_name": entry.spot_name,
                "player_count": entry.occupant_count,
            }
            for entry in collect_spot_occupancy(
                graph=self._spot_graph_repo.find_graph(),
                player_ids=self.get_player_ids(),
                player_life_query=self._player_life_query,
                scope=SpotOccupancyScope.MEETING_ELIGIBLE_PLAYERS,
            )
        ]
        recorder.record(
            TraceEventKind.WORLD_SPATIAL_METRICS,
            tick=tick,
            occupancy_scope="meeting_eligible_players",
            travel_scope="all_players_including_departed",
            spot_occupancy=occupancy,
            cumulative_travel_ticks_by_player={
                str(int(player_id)): self._cumulative_travel_ticks_by_player.get(
                    int(player_id), 0
                )
                for player_id in self.get_player_ids()
            },
        )

    def _maybe_close_meeting_on_timeout(self, tick: int) -> None:
        """沈黙上限 / tick 上限に達した会議を閉じる。

        会議が終わらないと、以降の run は移動も採取もできないまま tick を
        消費する。しかも「議論が続いている」ように見えるので、trace を読む
        まで気付けない。

        **打ち切りでも、投じられた票は集計する。** 捨てると「投票したのに
        何も起きなかった」になり、投票そのものが無意味に見える。
        """
        reason = self._game_phase_store.meeting_timeout_reason(tick=tick)
        if reason is None:
            return
        service = self._meeting_command_service
        if service is None:
            raise RuntimeError("MeetingCommandService is not wired")
        service.resolve_and_end(reason=reason)

    def set_trace_recorder(self, recorder: Any) -> None:
        """シナリオ実行 trace の recorder を後から差し込む (Phase 1d 配線)。

        ``create_session`` などで world_runtime を構築した後に
        外側から trace を有効化する用途。memo executor は lazy 構築なので
        既に作成済みでもこのフィールドが反映される。
        """
        self._trace_recorder = recorder
        # 市場の値動きは trace が一次データになる。recorder が差し込まれた
        # 時点で市場へも渡さないと、**run 後に価格の時系列が引けない**。
        market_service = getattr(self, "_market_service", None)
        if market_service is not None:
            market_service.set_trace_recorder(recorder, self.current_tick)
        # 既に memo executor が wire 済みなら作り直してから recorder を行き渡らせる
        if self._todo_tool_executor is not None:
            self._todo_tool_executor = None
            self._wire_auxiliary_tool_stack()
        # 短期記憶の構築時点では recorder が未確定なので、L4 / L5 と圧縮発火の
        # trace provider をここで注入する。実装差は getattr で吸収する。
        set_recorder = getattr(self._short_term_memory, "set_trace_recorder_provider", None)
        if callable(set_recorder):
            set_recorder(lambda: self._trace_recorder)
        set_tick = getattr(self._short_term_memory, "set_current_tick_provider", None)
        if callable(set_tick):
            set_tick(lambda: self.current_tick())

    @property
    def trace_recorder(self) -> Any:
        return self._trace_recorder

    def shutdown(self, timeout: Optional[float] = None) -> None:
        """非同期スケジューラ等の in-flight ジョブを drain して資源を解放する。

        PR #309: ``ThreadPoolEpisodicSubjectiveScheduler`` が裏で走っている
        LLM 補完を、ゲーム終了時に終わらせるための hook。``timeout`` 秒経っても
        終わらないジョブは諦めて cancel する (= テンプレ既定値が store に
        残るだけで損失は限定的)。

        本メソッドは複数回呼ばれても安全 (scheduler 側でも is_shutdown flag を
        持つ)。``timeout=None`` (既定) は完了まで無期限待機。
        """
        stack = self._episodic_stack
        if stack is None:
            return
        scheduler = stack.subjective_completion_scheduler
        if scheduler is None:
            return
        try:
            scheduler.shutdown(timeout=timeout)
        except Exception:
            logger.exception("episodic subjective scheduler shutdown failed")

    def set_tool_call_loop_guard(self, guard: Any) -> None:
        """``ToolCallLoopGuardService`` を後から注入する。

        presentation 層の wiring (= runtime_manager) で先に loop_guard を
        作って record_and_check を呼んでいる。同じ instance を prompt_builder
        にも渡して、instruction 末尾に「同じ手の繰り返し」prefix を載せる
        ために peek_streak される。``None`` を渡すと prefix は出ない。
        既に prompt_builder が組まれていた場合は cache を破棄して次回
        build 時に新 guard で組み直す。
        """
        self._injected_tool_call_loop_guard = guard
        self._cached_default_prompt_builder = None

    def set_simulation_llm_turn_trigger(
        self, trigger: Optional[ILlmTurnTrigger]
    ) -> None:
        """ティック後の :meth:`ILlmTurnTrigger.run_scheduled_turns` に使う実装を差し替える。

        プレゼン層の ``_WorldLlmWiring`` など、実際に LLM を起動するトリガに
        切り替える。単体デモの既定は :class:`WorldStandaloneNoopLlmTurnTrigger`。
        """
        self._simulation_service.set_llm_turn_trigger(trigger)

    def set_simulation_heartbeat_emitter(
        self, emitter: Optional[HeartbeatObservationEmitter]
    ) -> None:
        """ティック後の heartbeat emitter を注入する（未設定なら送信しない）。

        ``SpotGraphSimulationApplicationService`` の post-tick フックに委譲する。
        """
        self._simulation_service.set_heartbeat_emitter(emitter)

    def set_observation_turn_scheduler(
        self, scheduler: Optional[ObservationTurnScheduler]
    ) -> None:
        """speech などの observation で recipient のターンを積むスケジューラを注入する。

        ``create_session`` が ``ObservationTurnScheduler`` を組み立てた後に
        runtime へ渡す前提。注入されていない単体デモでは speech 配信は行わ
        れるがターン再スケジュールはされない。
        """
        self._observation_turn_scheduler = scheduler

    def do_speech(
        self,
        speaker_player_id: PlayerId,
        content: str,
        channel: SpeechChannel,
        target_player_id: Optional[PlayerId] = None,
    ) -> None:
        """speech_speak ツールの実行口。channel に応じて WHISPER/SAY/SHOUT で発話する。

        PlayerSpokeEvent を fire し、ObservationPipeline 経由で配信する。距離 gating
        (SoundPropagationService) は recipient strategy 側で行われる。

        Issue #264 後続で旧 do_say / do_whisper を統合した。SHOUT も同様に扱える。
        WHISPER のときだけ target_player_id が必須。
        """
        if self._speech_service is None:
            return
        target_id = (
            int(target_player_id.value)
            if target_player_id is not None
            else None
        )
        self._speech_service.speak(
            SpeakCommand(
                speaker_player_id=int(speaker_player_id.value),
                content=content,
                channel=channel,
                target_player_id=target_id,
            )
        )
        # 会議中の発言は沈黙上限の起点を進める。ここを忘れると、活発に議論
        # していても開始からの経過だけで打ち切られる。
        self._note_meeting_activity()

    def _note_meeting_activity(self) -> None:
        """発言があったことを会議に記録する (沈黙上限の起点を進める)。"""
        if self._game_phase_store.is_meeting():
            self._game_phase_store.note_activity(tick=int(self.current_tick()))

    def do_say(self, speaker_player_id: PlayerId, content: str) -> None:
        """[deprecated] do_speech(channel=SAY) を呼び出す薄い shim。新規コードは
        do_speech を直接使うこと。"""
        self.do_speech(speaker_player_id, content, SpeechChannel.SAY)

    def do_whisper(
        self,
        speaker_player_id: PlayerId,
        content: str,
        target_player_id: PlayerId,
    ) -> None:
        """[deprecated] do_speech(channel=WHISPER, target_player_id=...) を呼ぶ shim。"""
        self.do_speech(speaker_player_id, content, SpeechChannel.WHISPER, target_player_id)

    # ── 後方互換ヘルパー（テスト用） ──

    def build_observation(self, player_id: PlayerId) -> str:
        """E2E テスト用の簡易観測テキスト。build_llm_context のテキスト部分を返す。"""
        return self.build_llm_context(player_id).current_state_text

    def build_available_tools(self, player_id: PlayerId) -> str:
        """E2E テスト用のツール一覧テキスト。"""
        names = [d.name for d in self.get_tool_definitions(player_id=player_id)]
        return ", ".join(names)

    def build_system_prompt(self, player_id: PlayerId) -> str:
        """LLM に渡すシステムプロンプト。

        Issue #264 第16回実験で「player 2 が自呼びする」自呼び回帰が見つかったため、
        player_id ごとに persona を埋めた system prompt を持つよう拡張した。
        _world_llm_system_prompts_by_player_id に該当 id があればそれを返す
        (rich persona)、なければ legacy の _world_llm_system_prompt にフォールバック
        (単体プレイの旧挙動互換)。
        """
        per_player = self._world_llm_system_prompts_by_player_id.get(
            int(player_id.value) if hasattr(player_id, "value") else int(player_id)
        )
        if per_player is not None:
            return per_player
        return self._world_llm_system_prompt

    # ── 実 LLM パイプラインによる観測構築 ──

    def build_llm_context(self, player_id: PlayerId) -> LlmUiContextDto:
        """実際のフォーマッタ + UiContextBuilder を通した LLM 向けコンテキストを構築する。"""
        snap = self._state_builder.build_snapshot(int(player_id))
        if snap is None:
            return LlmUiContextDto(
                current_state_text="(このプレイヤーはまだグラフ上に配置されていません)",
                tool_runtime_context=ToolRuntimeContextDto.empty(),
            )
        dto = self._build_minimal_player_state_dto(player_id, snap)
        base_text = self._formatter.format(dto)
        result = self._ui_context_builder.build(base_text, dto)
        violations = find_prompt_argument_contract_violations(
            result.current_state_text,
            result.tool_runtime_context,
        )
        if violations:
            self._record_prompt_argument_contract_violations(player_id, violations)
        return result

    def _record_prompt_argument_contract_violations(
        self,
        player_id: PlayerId,
        violations: Tuple[PromptArgumentContractViolation, ...],
    ) -> None:
        """run 中の表記破れを trace に残し、実験自体は続行する。"""
        recorder = self._trace_recorder
        if recorder is None:
            return
        try:
            from ai_rpg_world.application.trace.events import TraceEventKind

            recorder.record(
                TraceEventKind.PROMPT_ARGUMENT_CONTRACT_VIOLATION,
                tick=self.current_tick(),
                player_id=player_id.value,
                violation_count=len(violations),
                violations=[
                    {
                        "value": violation.value,
                        "source": violation.source,
                        "target_label": violation.target_label,
                        "target_kind": violation.target_kind,
                    }
                    for violation in violations
                ],
            )
        except Exception:
            # run 中の記録失敗で実験データまで失わない。ただし
            # 表記の破れを静かにしないよう warning は必ず残す。
            logger.warning(
                "prompt argument contract violation trace recording failed "
                "(player_id=%s)",
                player_id.value,
                exc_info=True,
            )

    def _record_world_flag_change(self, change: WorldFlagChange) -> None:
        """実行中の flag 状態遷移を因果つきで trace に残す。

        snapshot 復元は過去の状態を置き直す操作で、新しい状態遷移ではない。
        source の判断は state に散らさず、trace へ変換するこの配線だけで行う。
        """
        if change.context.source is WorldFlagMutationSource.SNAPSHOT_RESTORE:
            return
        recorder = self._trace_recorder
        if recorder is None:
            return
        try:
            from ai_rpg_world.application.trace import TraceEventKind

            recorder.record(
                TraceEventKind.WORLD_FLAG_CHANGED,
                tick=self.current_tick(),
                player_id=change.context.actor_player_id,
                flag_name=change.flag_name,
                set=change.is_set,
                source=change.context.source.value,
                actor_player_id=change.context.actor_player_id,
            )
        except Exception:
            logger.warning(
                "WORLD_FLAG_CHANGED trace record failed: flag_name=%s",
                change.flag_name,
                exc_info=True,
            )

    def _validate_prompt_argument_contract_at_startup(self) -> None:
        """全 player の初期 prompt を検査し、壊れた実験を開始前に止める。"""
        failures: list[str] = []
        # build_snapshot は通常、初めて見た monster や倒れた人を通知する。
        # 読み取り専用の起動時検査で「一度きり」の観測を先に消費しない。
        with self._state_builder.suppress_observation_notifications():
            for status in self._player_status_repo.find_all():
                player_id = status.player_id
                result = self.build_llm_context(player_id)
                violations = find_prompt_argument_contract_violations(
                    result.current_state_text,
                    result.tool_runtime_context,
                )
                failures.extend(
                    f"player={player_id.value} source={violation.source} "
                    f"value={violation.value!r} target={violation.target_label} "
                    f"kind={violation.target_kind}"
                    for violation in violations
                )
        if failures:
            raise PromptArgumentContractError(
                "LLM prompt の tool 引数候補が引用符つきで表示されていません:\n"
                + "\n".join(failures)
            )

    def _validate_action_argument_classification_at_startup(self) -> None:
        """露出し得る全 tool schema の property が分類済みか確かめる。

        実行器の配線状態には触れず、spot catalog と全 memory catalog を直接見る。
        ``get_tool_definitions`` を使うと、この検査とは無関係な memory tool の
        配線検査まで前倒しされ、どの不変条件で起動が止まったかが混ざるため。

        現在の profile だけを見ると goal / memory 引数の追加を取りこぼし、初めて
        その経路を使う高コスト run まで欠落が潜伏するので、露出可能な全 schema
        を検査する。
        """

        definitions: list[ToolDefinitionDto] = []
        for tool_schema_mode in ("legacy", "reason_first"):
            definitions.extend(self._build_spot_tool_definitions(tool_schema_mode))
        definitions.extend(
            defn
            for defn, _ in get_memory_specs(
                todo_enabled=True,
                memo_enabled=True,
                episodic_explore_related_enabled=True,
                semantic_search_enabled=True,
                episodic_recall_enabled=True,
                recall_by_handle_enabled=True,
            )
        )
        definitions.append(
            assess_situation_definition(
                expected_result_policy=self._expected_result_policy
            )
        )
        missing = unclassified_action_argument_names(definitions)
        if missing:
            raise ActionArgumentClassificationError(
                "行動履歴での扱いが未分類の tool 引数があります: "
                + ", ".join(missing)
            )

    def _compute_task_progress_line(self) -> Optional[str]:
        """作業の進み具合を 1 行で返す。作業条件が無いシナリオでは None。

        本家のタスクバーにあたる。クルーにとって**勝ち筋が進んでいるかの
        唯一の指標**で、インポスターが作業のふりをしても増えない。

        engine 側の事情としても要る。作業は別々の部屋に置かれるので、
        **他人が何を終わらせたかは観測として届かない**。進みが見えないと、
        各エージェントは自分がやったぶんしか知らないまま「まだ全然進んで
        いない」と誤認し続ける。

        **総数だけを出す。** 誰が終わらせたかを出すと偽装が成立しない
        (作業のふりをしても即座に割れる)。どの作業が残っているかも出さない。
        作業は場所と紐づくので、消去法で「あそこに誰が居たか」が割れる。
        """
        from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import (
            GameEndConditionTypeEnum,
        )

        flags = self._world_flag_state.as_frozen_set()
        parts: List[str] = []
        for cond in self.scenario.win_conditions:
            if cond.condition_type is not GameEndConditionTypeEnum.FLAGS_SET_AT_LEAST:
                continue
            declared = tuple(cond.required_flags or ())
            if not declared:
                continue
            done = sum(1 for name in declared if name in flags)
            need = int(cond.min_set_count or len(declared))
            remaining = max(0, need - done)
            text = f"作業の進み: {done}/{len(declared)}"
            if remaining > 0:
                # 総数だけだと、あと何個で勝てるのかが読めない。締切と同じで
                # 「あといくつか」が分からないと配分を決められない。
                text += f" (あと {remaining})"
            else:
                text += " (必要数に到達)"
            parts.append(text)
        if not parts:
            return None
        return " / ".join(parts)

    def _compute_meeting_status_line(self) -> Optional[str]:
        """会議中なら、状況を 1 行にまとめて返す。自由時間なら None。

        入れる情報は 3 つ。

        - 話し合いの最中であること (= 移動や採取ができない理由)
        - 打ち切りまでの残り tick。**締切が見えないと「もう投票すべきか」を
          判断できない。** 本家の会議に見えるタイマーがあるのと同じ役割
        - 誰が呼んだか。議論の出発点になり、会議のあいだ何度も参照される

        沈黙による終了までの残りは出さない。発言のたびに戻るので、締切と
        して読むと誤解を招く (「あと 2 tick」と出た次のターンに 6 に戻る)。
        """
        store = self._game_phase_store
        if not store.is_meeting():
            return None
        current = store.current
        elapsed = int(self.current_tick()) - current.started_at_tick
        remaining = max(0, store.meeting_tick_limit - elapsed)
        parts = ["話し合いの最中。全員がこの場に集まっている"]
        initiator = self._meeting_initiator_display_name()
        if initiator:
            parts.append(f"呼びかけたのは{initiator}")
        # 単位は世界の時計に揃える。**tick は engine の語彙で、世界の中に
        # 無い** (#892)。地図で直したのと同じ形が、ここに残っていた。
        # 換算は _minutes_per_tick を通す (地図と時計と別々に持つとずれる)。
        # 時間と**手番の残り**を両方出す。
        #
        # run 009 の失敗は「時間」ではなく手番の読み違いだった。24 回喋って
        # 9 回 `wait` が出たのは「待てば次がある」と読んだから。**30 分と
        # 言われても、自分があと何回動けるかは分からない** (claude の指摘)。
        minutes = _minutes_per_tick(self.scenario)
        if minutes:
            parts.append(f"打ち切りまであと {remaining * minutes} 分 (あと {remaining} 回ぶん)")
        else:
            parts.append(f"打ち切りまであと {remaining} 回ぶん")
        # 締切が近いほど強く言う。
        #
        # 実 run 009 は 6 tick を使い切って 24 回喋り、**投票は 1 票だけ**
        # だった。9 回 `wait` が出ていて、「待てば投票の機会が来る」と読んで
        # いるように見える。実際には待つと打ち切られて誰も追放されない。
        # 残り回数は出ていたが、**それが何を意味するかが書かれていなかった。**
        if remaining <= _MEETING_URGENT_REMAINING_TICKS:
            parts.append("いま投票しないと、誰も追放されないまま終わる")
        else:
            parts.append("投票しないまま打ち切られると、誰も追放されない")
        return "。".join(parts) + "。"

    def _meeting_initiator_display_name(self) -> Optional[str]:
        """招集者の表示名。引けなければ None (その節だけ落ちる)。

        名前の解決は `get_player_name` に寄せる。フェーズ変化の観測で使って
        いるのと同じ経路にしておかないと、観測では「クゼが呼びかけた」なのに
        現在状態では別の呼び方、という食い違いが起きる。
        """
        initiator_id = self._game_phase_store.current.initiator_player_id
        if initiator_id is None:
            return None
        try:
            return self.get_player_name(PlayerId(initiator_id)) or None
        except Exception:
            return None

    def _compute_tick_budget_remaining(self) -> Optional[int]:
        """シナリオの lose_conditions に TICK_LIMIT があれば残り tick を返す。

        WIN 条件には触れず「時間切れまでの猶予」だけ LLM に伝えるためのメタ情報。
        複数の TICK_LIMIT 条件があるときは最小値 (一番早く切れるもの) を採用。
        """
        from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import (
            GameEndConditionTypeEnum,
        )
        limits: List[int] = []
        for lc in self.scenario.lose_conditions:
            if lc.condition_type != GameEndConditionTypeEnum.TICK_LIMIT:
                continue
            if lc.tick_limit is None:
                continue
            limits.append(int(lc.tick_limit))
        if not limits:
            return None
        return max(0, min(limits) - self._tick)

    def _build_minimal_player_state_dto(
        self, player_id: PlayerId, snap: Any,
    ) -> PlayerCurrentStateDto:
        time_label = self._time_label()
        return PlayerCurrentStateDto(
            player_id=int(player_id),
            player_name=self.get_player_name(player_id),
            current_spot_id=None,
            current_spot_name=snap.current_spot_name,
            current_spot_description=snap.current_spot_description,
            x=None, y=None, z=None,
            current_player_count=0,
            current_player_ids=set(),
            connected_spot_ids=set(),
            connected_spot_names=set(),
            weather_type="不明",
            weather_intensity=0.0,
            current_terrain_type=None,
            visible_objects=[],
            view_distance=0,
            available_moves=None,
            total_available_moves=None,
            attention_level=AttentionLevel.FULL,
            spot_graph_snapshot=snap,
            current_game_time_label=time_label,
            tick_budget_remaining=self._compute_tick_budget_remaining(),
            meeting_status_line=self._compute_meeting_status_line(),
            task_progress_line=self._compute_task_progress_line(),
            game_phase=self._game_phase_store.current.phase,
        )

    @property
    def tool_exposure(self) -> ToolExposure:
        """この世界に存在するツールの判断。

        ツール定義を組む側と、プロンプト本文を書く側の**両方**がここを見る。
        片方だけが見ていたために、無効化したツールが行動候補として宣伝され
        続けていた (`tend_to_player`)。
        """
        cached = getattr(self, "_tool_exposure_cache", None)
        if cached is None:
            cached = ToolExposure.from_scenario(
                self.scenario, meeting_declared=self._meeting_enabled
            )
            self._tool_exposure_cache = cached
        return cached

    def _without_tools_the_scenario_disabled(
        self, definitions: List[ToolDefinitionDto]
    ) -> List[ToolDefinitionDto]:
        """シナリオが「この世界では出さない」と宣言したツールを落とす。

        **世界の中身に無いものを出さない。** モンスターの居ない世界に
        ``spot_graph_attack`` が並び続けるのが動機だった。対象候補が永久に
        空なのに毎ターン選択肢に載るので、実 run 007 ではインポスターが
        3 手を捨てている。「選べるのに必ず失敗する手」を並べない、という
        #860 と同じ判断。

        engine 側に「モンスターが居なければ attack を落とす」と書くことも
        できたが、**何を出さないかは世界ごとに違う**。シナリオが決める形に
        して、ツールを 1 つ足すたびに engine へ条件を書き足さなくてよく
        する。

        実在しない名前は起動時に落とす。黙って無視すると「無効化した
        つもりが出たまま」になり、run を 1 本流すまで気付かない。

        判定は run 中ずっと変わらないので、プレフィックスキャッシュ
        (設計判断 #1) には影響しない。フェーズによる出し分けと違い、
        同じ run の中で並びが揺れることが無い。
        """
        disabled = self._validate_disabled_tool_names()
        if not disabled:
            return definitions
        return [defn for defn in definitions if defn.name not in disabled]

    def _validate_disabled_tool_names(self) -> tuple:
        """``disabled_tools`` の名前が実在することを確かめ、その集合を返す。

        実在しない名前を黙って無視すると「無効化したつもりが出たまま」に
        なる。run を 1 本流し終えて無駄手の山を見るまで気付かない。

        エラーには書ける名前の一覧を添える。名前を間違えた人が次に要るのは
        正解の一覧で、「不正な名前です」だけでは同じ間違いを繰り返す。
        """
        disabled = self.scenario.disabled_tools
        # loader は必ず tuple を返す。tuple でないのはテスト用の代役なので、
        # 何も落とさない。
        if not isinstance(disabled, tuple) or not disabled:
            return ()
        known = {defn.name for defn, _ in get_spot_graph_specs()}
        unknown = [name for name in disabled if name not in known]
        if unknown:
            raise ToolExposureConfigurationError(
                "disabled_tools に実在しないツール名があります: "
                f"{', '.join(unknown)} / 指定できるのは: {', '.join(sorted(known))}"
                + _where_to_turn_off_instead(unknown)
            )
        return tuple(disabled)

    def get_tool_definitions(
        self,
        *,
        tool_schema_mode: str = "legacy",
        as_meeting_phase: Optional[bool] = None,
        player_id: Optional[PlayerId] = None,
        for_every_player: bool = False,
    ) -> List[ToolDefinitionDto]:
        """LLM に渡されるツール定義（OpenAI tools 形式）を返す。

        ``_include_todo_tools=False`` の場合は TODO 系 (todo_add / todo_list /
        todo_complete) を除外し、spot_graph_* + speech (say / whisper) のみ
        を返す。LLM が「TODO 操作の連打」に逃げない条件で挙動を比較するため
        の純スポットグラフモード (B-4 / Issue #155 の判断材料)。
        この粗いモードでは個別の記憶ツール露出フラグも評価せず、補助ツール
        全体を隠す。

        ツール露出の強制点はこのメソッドに集約する。シナリオ由来の
        ``prepare_action`` 導出露出と、設定由来の記憶系ツール露出を同じ場所で
        決めることで、「なぜ tool が LLM に出ないか」の追跡点を分散させない。

        記憶系ツールは、該当 runtime config が true かつ実行器が組めた場合だけ
        露出する。config true なのに前提配線が無い場合は fail-fast する。
        比較実験で「有効にしたつもりが黙って無効」になる静かな失敗を避けるため。

        ``tool_schema_mode="legacy"`` は従来互換。``"reason_first"`` では
        ``assess_situation`` を加え、行動 tool から step1 所有の
        ``inner_thought`` / ``expected_result`` だけを外す。

        reason_first では ``assess_situation`` を必ず末尾に置く。action_phase
        は末尾の評価 tool だけを落とすため、先頭の行動 tool 定義ブロックを
        assess_phase とバイト単位で揃えやすくする。

        本人へ提示する場合は ``player_id``、起動時に全員分の和集合を検査する
        場合だけ ``for_every_player=True`` を指定する。どちらも無い呼び出しを
        許すと、本人固有の状態を運び忘れても全体向けへ黙って縮退するため、
        ちょうど一方だけを必須にする。
        """
        audience_count = int(player_id is not None) + int(for_every_player)
        if audience_count != 1:
            raise ValueError(
                "get_tool_definitions は player_id または "
                "for_every_player=True のどちらか一方を必要とします"
            )
        if tool_schema_mode not in {"legacy", "reason_first"}:
            raise ValueError("tool_schema_mode must be 'legacy' or 'reason_first'")
        spot = self._build_spot_tool_definitions(tool_schema_mode)
        in_meeting = (
            self._game_phase_store.is_meeting()
            if as_meeting_phase is None
            else bool(as_meeting_phase)
        )
        # 2 つの問いを両方通す入口を使う。片方だけ呼ぶと無効化が効かない。
        by_name = {d.name: d for d in spot}
        common_names, phase_names = self.tool_exposure.split_for_phase(
            by_name.keys(),
            in_meeting=in_meeting,
            voting_completed=(
                player_id is not None
                and in_meeting
                and self._game_phase_store.has_voted(player_id)
            ),
        )
        common_spot = [by_name[n] for n in common_names]
        phase_spot = [by_name[n] for n in phase_names]
        if (
            player_id is not None
            and self._player_perception_policy.is_departed(player_id)
        ):
            departed_tool_names = frozenset(
                {
                    TOOL_NAME_SPEECH,
                    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
                    TOOL_NAME_SPOT_GRAPH_INTERACT,
                    TOOL_NAME_SPOT_GRAPH_LISTEN,
                    TOOL_NAME_SPOT_GRAPH_WAIT,
                }
            )
            common_spot = [
                definition
                for definition in common_spot
                if definition.name in departed_tool_names
            ]
            phase_spot = [
                definition
                for definition in phase_spot
                if definition.name in departed_tool_names
            ]
        assessment = (
            [
                assess_situation_definition(
                    expected_result_policy=self._expected_result_policy
                )
            ]
            if tool_schema_mode == "reason_first"
            else []
        )
        definitions = common_spot + phase_spot
        if self._include_todo_tools:
            definitions += self._build_memory_tool_definitions()
        by_name = {definition.name: definition for definition in definitions}
        ordered_names = self.tool_exposure.order_for_payload(by_name.keys())
        return [by_name[name] for name in ordered_names] + assessment

    def _build_spot_tool_definitions(
        self, tool_schema_mode: str
    ) -> List[ToolDefinitionDto]:
        """この世界に在る spot tool を、フェーズを問わずすべて返す。

        並べ替えとフェーズの出し分けは呼び出し側。ここは「在るか無いか」
        だけを決める。
        """
        spot = [
            self._with_goal_update_if_enabled(
                self._with_expected_result_if_enabled(defn)
            )
            for defn, _ in get_spot_graph_specs()
        ]
        # 「この世界に存在するツールか」は ToolExposure が一括で答える。
        # 同時行動 / 会議機構 / シナリオの無効化宣言を 3 つ別々に書いて
        # いたが、**プロンプト本文の側から同じ判断を参照できなかった**。
        # 集めた結果、状態ビルダーからも同じ答えを引ける。
        exposure = self.tool_exposure
        spot = [defn for defn in spot if exposure.is_exposed(defn.name)]
        if tool_schema_mode == "reason_first":
            spot = [strip_reason_first_action_subjective_schema(d) for d in spot]
        return spot

    def _build_memory_tool_definitions(self) -> List[ToolDefinitionDto]:
        """実験設定が要求する記憶系ツールを返す。

        **世界ではなく実験の設定**で決まるので `ToolExposure` には置かない。
        同じシナリオを profile 違いで回すときに変わるのがこちら。

        設定が true なのに実行器が組めていなければ fail-fast する。黙って
        false へ縮退すると、比較実験で「有効にしたつもりが無効だった」に
        なる。
        """
        # Issue #526 後続: tool を expose するタイミングで auxiliary stack を
        # 確実に wire しておく (= 「定義は出すが handler が無い」状態を防ぐ)。
        # idempotent なので毎回呼んで OK。
        if self._episodic_stack is not None:
            self._wire_auxiliary_tool_stack()
        cfg = self._runtime_config
        episodic_recall_enabled = self._resolve_requested_memory_tool_enabled(
            requested=bool(getattr(cfg, "episodic_recall_enabled", False)),
            executor=self._memory_recall_tool_executor,
            tool_name=TOOL_NAME_MEMORY_RECALL_EPISODES,
            flag_name="EPISODIC_RECALL_ENABLED",
        )
        episodic_explore_related_enabled = (
            self._resolve_requested_memory_tool_enabled(
                requested=bool(
                    getattr(cfg, "episodic_explore_related_enabled", False)
                ),
                executor=self._memory_explore_related_tool_executor,
                tool_name=TOOL_NAME_MEMORY_EXPLORE_RELATED,
                flag_name="EPISODIC_EXPLORE_RELATED_ENABLED",
            )
        )
        semantic_search_enabled = self._resolve_requested_memory_tool_enabled(
            requested=bool(getattr(cfg, "semantic_search_enabled", False)),
            executor=self._semantic_memory_search_tool_executor,
            tool_name=TOOL_NAME_MEMORY_SEARCH_SEMANTIC,
            flag_name="SEMANTIC_SEARCH_ENABLED",
        )
        return [
            defn
            for defn, _ in get_memory_specs(
                todo_enabled=True,
                memo_enabled=bool(getattr(cfg, "memo_tools_enabled", True)),
                episodic_explore_related_enabled=episodic_explore_related_enabled,
                semantic_search_enabled=semantic_search_enabled,
                episodic_recall_enabled=episodic_recall_enabled,
                recall_by_handle_enabled=(
                    self._memory_recall_by_handle_tool_executor is not None
                ),
            )
        ]




    @staticmethod
    def _resolve_requested_memory_tool_enabled(
        *,
        requested: bool,
        executor: Optional[Any],
        tool_name: str,
        flag_name: str,
    ) -> bool:
        """設定 true の記憶ツールに実行器が無ければ起動時に落とす。

        false のときは実行器があっても expose しない。true のときに実行器が
        無いまま黙って false へ縮退すると、比較実験で「条件を変えたつもりが
        変わっていない」静かな失敗になる。
        """
        if not requested:
            return False
        if executor is None:
            raise ToolExposureConfigurationError(
                f"{flag_name}=true requires an executor for {tool_name}, "
                "but the runtime memory stack is not wired. Enable the required "
                "episodic/semantic prerequisites or turn the flag off."
        )
        return True

    def _memo_tools_enabled(self) -> bool:
        """memo ツールを LLM に露出する設定か。

        露出を切る実験腕では、tool 定義だけでなく prompt の未完了 memo section
        も同時に止める。存在しない memo_done への誘導を残さないため。
        """
        return bool(getattr(self._runtime_config, "memo_tools_enabled", True))

    # Prediction (#526 v0): expected_result 露出の対象 tool。記録経路 (do_* →
    # _record_action_result) に subjective を配線済みの core action だけに限定する
    # (= 露出範囲と structured 保存範囲を一致させる)。listen / item 系 / attack
    # 等は generic 記録経路が未配線なので露出しない。
    _EXPECTED_RESULT_TARGET_TOOLS = frozenset(
        {
            TOOL_NAME_SPOT_GRAPH_EXPLORE,
            TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            TOOL_NAME_SPOT_GRAPH_INTERACT,
            TOOL_NAME_SPOT_GRAPH_WAIT,
        }
    )

    def _with_expected_result_if_enabled(
        self, definition: ToolDefinitionDto
    ) -> ToolDefinitionDto:
        """policy が off 以外かつ対象 tool なら expected_result を schema に足す。

        off (既定) では definition をそのまま返す = 挙動不変。optional は properties
        にのみ、required は required にも追加する。
        """
        if self._expected_result_policy == "off":
            return definition
        if definition.name not in self._EXPECTED_RESULT_TARGET_TOOLS:
            return definition
        return with_expected_result_schema(
            definition, required=self._expected_result_policy == "required"
        )

    def _with_goal_update_if_enabled(
        self, definition: ToolDefinitionDto
    ) -> ToolDefinitionDto:
        """P6/P8: GOAL_REVISION_ENABLED ON なら world-action tool に optional な

        ``goal_update`` (立て直し) と ``goal_outcome`` (清算) を足す。**run 全体で
        常時**適用するので tick 間で schema は byte 不変 (設計判断 #1 遵守)。
        OFF (既定) では definition をそのまま返す。
        """
        if not self._goal_revision_enabled:
            return definition
        return with_goal_outcome_schema(with_goal_update_schema(definition))

    # ── 観測パイプライン: イベントを処理して各プレイヤーに配信 ──

    def _process_graph_events(self) -> None:
        """グラフ集約からイベントを収集し、PipelineEventPublisher 経由で
        各プレイヤーに配信する。

        Issue #276 経路二重化解消: 旧実装は ``_obs_pipeline.run`` + 直接
        ``_obs_buffer.append`` で配信していたが、これでは:
        - ``_observation_appender`` を経由しないので observation の trace
          記録 (Issue #276) が漏れる
        - ``_observation_turn_scheduler.maybe_schedule`` を呼ばないので、
          graph aggregate 由来の観測 (door state change / ambient sound 等)
          で listener のターンが積まれず、`schedules_turn=True` が機能しない

        speech / interaction で使う ``PipelineEventPublisher.publish_all`` に
        統一することで pipeline → appender → scheduler の一本道に揃える。
        """
        graph = self._spot_graph_repo.find_graph()
        # silent failure fix: publisher が None のときは events を取り出す前に
        # 早期 return する。先に list(graph.get_events()) + clear_events() を
        # 呼ぶと、publisher が無い段階でイベントが clear されて永久に失われる
        # (旧コードでは「構築途中だから silent skip」だった)。
        if self._speech_event_publisher is None:
            return
        events = list(graph.get_events())
        graph.clear_events()
        if not events:
            return
        self._speech_event_publisher.publish_all(events)

    def _emit_observation_directly(
        self,
        player_id: PlayerId,
        output: ObservationOutput,
    ) -> None:
        """pipeline を介さず特定プレイヤーへ観測を 1 件届ける共通経路。

        scenario_event / weather など「pipeline での recipient 解決が要らない
        既に届け先が決まっている」観測の単一経路。``_observation_appender``
        と ``_observation_turn_scheduler`` を両方経由するので trace 記録と
        turn schedule の漏れを起こさない。
        """
        appender = self._observation_appender
        if appender is None:
            # 構築途中で呼ばれた場合の防御 (PipelineEventPublisher と同様)。
            return
        # tz-aware UTC で統一: HeartbeatObservationEmitter /
        # ActionFailedObservationEmitter が aware を発行するため、world_runtime
        # 経路の naive と混ざると EpisodicChunkCoordinator の obs_slice
        # フィルタで TypeError になる。詳細: docs/episodic_memory フォローアップ。
        appender.append(
            player_id, output, datetime.now(timezone.utc), self._time_label()
        )
        scheduler = self._observation_turn_scheduler
        if scheduler is not None:
            scheduler.maybe_schedule(player_id, output)

    def _get_prediction_context_ledger(self) -> Optional[PredictionContextLedger]:
        """予測誤差統一設計 U1 の ``PredictionContextLedger`` を lazy 構築・共有する。

        ``DefaultPromptBuilder`` (発行元) と ``ActionResultRecorder``
        (消費元) が同じ instance を参照する必要があるため、
        ``_cached_default_prompt_builder`` と同じ lazy キャッシュパターンで
        world_runtime が唯一の owner になる。

        ``ResolvedLlmRuntimeConfig.prediction_context_id_enabled`` で default OFF
        (共通規約 §0: 新機構は明示的に有効化しない限り動かさない)。OFF の間は
        None を返し、builder / recorder 側は ledger 未注入と同じ経路
        (= prediction_context_id は常に None) を通る。
        """
        sentinel_computed = getattr(
            self, "_prediction_context_ledger_computed", False
        )
        if sentinel_computed:
            return getattr(self, "_prediction_context_ledger_instance", None)

        from ai_rpg_world.application.llm.wiring.feature_flags import (
            log_prediction_context_id_state,
        )

        cfg = getattr(self, "_runtime_config", None)
        enabled = (
            bool(cfg.prediction_context_id_enabled)
            if cfg is not None
            else False
        )
        log_prediction_context_id_state(enabled)
        ledger = PredictionContextLedger() if enabled else None
        self._prediction_context_ledger_instance = ledger
        self._prediction_context_ledger_computed = True
        return ledger

    def _record_action_result(
        self,
        player_id: PlayerId,
        action_summary: str,
        result_summary: str,
        *,
        tool_name: str,
        identifier_arguments: Optional[Mapping[str, str]] = None,
        free_text_argument_names: tuple[str, ...] = (),
        success: bool = True,
        error_code: Optional[str] = None,
        scene_boundary: bool = False,
        inner_thought: Optional[str] = None,
        expected_result: Optional[str] = None,
        intention: Optional[str] = None,
        emotion_hint: Optional[str] = None,
    ) -> None:
        """action_result_store に 1 件積み、episodic chunk_coordinator を起動する。

        ``tool_name`` は必須引数: 第20回実験で「episode_cues に常に
        ``action:unknown_tool`` が立つ」問題が観測されたため、呼び出し側で
        必ず LLM tool 名 (例: ``TOOL_NAME_SPOT_GRAPH_TRAVEL_TO``) を明示する。
        ``success`` / ``error_code`` も同様に「常に ``outcome:success`` が立つ」
        ノイズの原因なので、失敗を検知できる経路は明示的に渡す。

        ``scene_boundary``: その行動がエピソード記憶の「シーン切り替え」を
        意味するかどうか。cognitive science の "doorway effect" を反映して、
        spot 遷移成功時は True を渡すと chunk が閉じやすくなる (Issue #311 後続)。

        ``inner_thought`` / ``expected_result`` / ``intention`` / ``emotion_hint``: LLM が行動前に
        宣言した主観入力 (予測 / 目的 / 感情)。予測誤差駆動の学習ループ
        (#526) の入力。do_* 経由で raw args 由来の値が渡る (U2)。露出スキーマが
        OFF の間は全 None なので記録挙動は不変。
        """
        # U1 (#526 後続): append → chunk write → semantic promotion (escape baseline
        # の順序・error isolation) を共有 ActionResultRecorder に委譲する。挙動は
        # #553 で contract 化済みで不変。subjective fields (expected_result 等) は
        # U2 で do_* → ここ → recorder と配線した (露出 OFF の間は None)。
        # tz-aware UTC で統一 (詳細は _emit_observation_directly のコメント参照)。
        # 予測誤差統一設計 U1: prompt_builder.build() が発行した
        # prediction_context_id をこの record() が consume できるよう、
        # builder と同じ ledger instance を共有する。
        recorder = ActionResultRecorder(
            self._action_result_store,
            logger=logger,
            prediction_context_ledger=self._get_prediction_context_ledger(),
        )
        acting = self._acting_being_for(player_id)
        recorder.record(
            player_id,
            action_summary=action_summary,
            result_summary=result_summary,
            occurred_at=datetime.now(timezone.utc),
            tool_name=tool_name,
            identifier_arguments=identifier_arguments,
            free_text_argument_names=free_text_argument_names,
            success=success,
            error_code=error_code,
            scene_boundary=scene_boundary,
            inner_thought=inner_thought,
            expected_result=expected_result,
            intention=intention,
            emotion_hint=emotion_hint,
            # Issue #311 後続: bucket 内 actions の tick 差で TEMPORAL_GAP 判定するため
            occurred_tick=self.current_tick(),
            # 描画時刻から相対ラベルを再計算せず、記録時の世界時刻を固定する。
            game_time_label=self._time_label(),
            episodic_stack=self._episodic_stack if acting is not None else None,
            being_id=acting.being_id if acting is not None else None,
        )

    def _drain_buffer_to_short_term_memory(self, player_id: PlayerId) -> List[ObservationEntry]:
        """観測バッファを短期記憶へ移し、溢れた観測を返す。"""
        drained = self._obs_buffer.drain(player_id)
        if not drained:
            return []
        return self._short_term_memory.append_all(player_id, drained)

    def _wire_auxiliary_tool_stack(self) -> None:
        """TODO ツール実行器を遅延初期化する。

        Phase 3 Step 3a-3: memo は being_id 経路必須なので、ここで
        ``BeingRepository`` + ``BeingAttachmentResolver`` + provisioning を
        構築する。executor 自体は Resolver を持たず、
        ``run_llm_auxiliary_tool`` が ``ensure_attached`` のあと
        ``resolve_being_id`` して ``ActingBeing`` を handler に渡す。

        Issue #526 後続: episodic_stack が wire 済なら memory_recall_episodes
        の executor も組み立てる (idempotent)。
        """
        # 既に両方 wire 済ならスキップ。recall executor は episodic_stack の
        # 注入タイミング次第で「todo は wire 済だが recall がまだ」になり得る
        # ため、各々の None check で個別に判定する。
        if self._todo_tool_executor is not None:
            self._wire_memory_recall_executor_if_possible()
            return
        from ai_rpg_world.application.being.being_provisioning_service import (
            BeingProvisioningService,
        )
        from ai_rpg_world.application.being.being_attachment_resolver import (
            BeingAttachmentResolver,
        )
        from ai_rpg_world.domain.world.value_object.world_id import (
            DEFAULT_SINGLE_WORLD_ID,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
            InMemoryBeingRepository,
        )

        if not hasattr(self, "_aux_being_repository"):
            self._aux_being_repository = InMemoryBeingRepository()
            self._aux_being_provisioning = BeingProvisioningService(
                self._aux_being_repository
            )
            self._aux_being_resolver = BeingAttachmentResolver(
                self._aux_being_repository
            )
            self._aux_being_default_world_id = DEFAULT_SINGLE_WORLD_ID

        self._todo_tool_executor = TodoToolExecutor(
            self._todo_store,
            short_term_memory=self._short_term_memory,
            action_result_store=self._action_result_store,
            current_tick_provider=self.current_tick,
            trace_recorder=self._trace_recorder,
        )
        # U5 (MEMO_DISTILL): executor を作り直したら memo_distill transcriber を
        # 再適用する。これがないと set_trace_recorder 等の作り直し経路で
        # transcriber が静かに失われる (実験 run で memo→evidence 蒸留が
        # 0 件になっていた原因)。create_world_runtime が transcriber を
        # 構築して runtime._memo_distill_transcriber に格納した後の作り直しで
        # 効く (初回 wire 時点では None なので no-op)。
        if self._memo_distill_transcriber is not None:
            self._todo_tool_executor.set_memo_distill_transcriber(
                self._memo_distill_transcriber
            )
        self._wire_memory_recall_executor_if_possible()

    def _wire_memory_recall_executor_if_possible(self) -> None:
        """記憶系の能動ツール executor を idempotent に組み立てる。

        episodic_stack が無いと episode store / noun_matcher にアクセス
        できないため、その場合は executor を作らない。LLM への露出可否は
        ``get_tool_definitions`` で runtime config と executor の AND として
        決める。``_aux_being_resolver`` / ``_aux_being_default_world_id`` は
        ``_wire_auxiliary_tool_stack`` 内で先に初期化される前提。

        PR-D fix: 旧実装は冒頭で ``_memory_recall_tool_executor`` の有無で
        早期 return していたが、それだと PR-D で追加した
        ``_memory_recall_by_handle_tool_executor`` の build が
        ``recall_episodes`` 既存時にスキップされ、tool は spec に出るのに
        handler が登録されないため LLM が呼ぶと「未対応のツールです」が
        返る silent failure になっていた。早期 return を外し、各 executor の
        個別 idempotent ガードに任せる形に変える。
        """
        if self._episodic_stack is None:
            return
        if not hasattr(self, "_aux_being_resolver"):
            return
        from ai_rpg_world.application.llm.services.executors.episodic_memory_recall_tool_executor import (
            EpisodicMemoryRecallToolExecutor,
        )
        from ai_rpg_world.application.llm.services.subjective_time import utc_now

        # idempotent ガード: 既に build 済なら再構築しない (= 既存挙動を保つ)
        if self._memory_recall_tool_executor is None:
            self._memory_recall_tool_executor = EpisodicMemoryRecallToolExecutor(
                episode_store=self._episodic_stack.episode_store,
                noun_matcher=self._episodic_stack.noun_matcher,
                time_provider=utc_now,
            )

        if self._memory_explore_related_tool_executor is None:
            link_store = getattr(self._episodic_stack, "memory_link_store", None)
            link_service = getattr(self._episodic_stack, "link_service", None)
            afterglow_store = getattr(self._episodic_stack, "afterglow_store", None)
            recall_slot_store = getattr(
                self._episodic_stack,
                "recall_slot_store",
                None,
            )
            if (
                link_store is not None
                and link_service is not None
                and afterglow_store is not None
                and recall_slot_store is not None
            ):
                from ai_rpg_world.application.llm.services.executors.episodic_memory_explore_tool_executor import (
                    EpisodicMemoryExploreToolExecutor,
                )

                self._memory_explore_related_tool_executor = (
                    EpisodicMemoryExploreToolExecutor(
                        episode_store=self._episodic_stack.episode_store,
                        link_store=link_store,
                        link_service=link_service,
                        afterglow_store=afterglow_store,
                        slot_store=recall_slot_store,
                    )
                )

        if self._semantic_memory_search_tool_executor is None:
            semantic_store = getattr(
                self._episodic_stack, "semantic_memory_store", None
            )
            if semantic_store is not None:
                from ai_rpg_world.application.llm.services.executors.semantic_memory_search_tool_executor import (
                    SemanticMemorySearchToolExecutor,
                )

                self._semantic_memory_search_tool_executor = (
                    SemanticMemorySearchToolExecutor(
                        semantic_store,
                    )
                )

        # PR-D: memory_recall_by_handle (afterglow handle → 本文 + slot 再注入)。
        # afterglow_store + slot_store が両方揃っていなければ意味がないので
        # 構築をスキップ (= LLM にも見せず handler も登録しない、graceful fallback)。
        afterglow_store = getattr(self._episodic_stack, "afterglow_store", None)
        slot_store = getattr(self._episodic_stack, "recall_slot_store", None)
        if (
            self._memory_recall_by_handle_tool_executor is None
            and afterglow_store is not None
            and slot_store is not None
        ):
            from ai_rpg_world.application.llm.services.executors.episodic_memory_recall_by_handle_tool_executor import (
                EpisodicMemoryRecallByHandleToolExecutor,
            )
            self._memory_recall_by_handle_tool_executor = (
                EpisodicMemoryRecallByHandleToolExecutor(
                    episode_store=self._episodic_stack.episode_store,
                    afterglow_store=afterglow_store,
                    slot_store=slot_store,
                    slot_capacity=getattr(
                        self._episodic_stack, "recall_slot_capacity", 4
                    ),
                    current_tick_provider=lambda: self.current_tick(),
                )
            )

    @property
    def aux_being_resolver(self):
        """Phase 3 Step 3a-3: auxiliary tool stack の ``_aux_being_resolver`` 公開。
        ``_acting_being_for`` 等が ``_wire_auxiliary_tool_stack`` 経由で Being を
        解決する。``_wire_auxiliary_tool_stack`` を呼んでいないと None。
        """
        return getattr(self, "_aux_being_resolver", None)

    @property
    def aux_being_default_world_id(self):
        """Phase 3 Step 3a-3: aux Being の default WorldId 公開アクセサ。"""
        return getattr(self, "_aux_being_default_world_id", None)

    def _acting_being_for(self, player_id: PlayerId) -> Optional[ActingBeing]:
        self._wire_auxiliary_tool_stack()
        self._aux_being_provisioning.ensure_attached(player_id)
        being_id = self._aux_being_resolver.resolve_being_id(
            self._aux_being_default_world_id, player_id
        )
        if being_id is None:
            return None
        return ActingBeing(player_id=player_id, being_id=being_id)

    def run_llm_auxiliary_tool(
        self, player_id: PlayerId, name: str, arguments: Dict[str, Any]
    ) -> LlmCommandResultDto:
        """TODO 系ツール および memory_recall_episodes を実行する。

        Phase 3 Step 3a-3: memo handler を起動する前に player_id に Being が
        attach されていることを保証する (= TodoToolExecutor が being_id 経路を
        通れるようにする)。

        Issue #526 後続: ``memory_recall_episodes`` も同じ aux Being 経路で
        動くため、handler 辞書に merge する。executor が wire されていない
        (= ``_episodic_stack=None``) なら memory_recall は未対応扱いになる。
        """
        self._wire_auxiliary_tool_stack()
        acting = self._acting_being_for(player_id)
        if acting is None:
            return LlmCommandResultDto(
                success=False,
                message="Being is not attached to this player.",
                error_code="INVALID_STATE",
            )
        assert self._todo_tool_executor is not None
        handlers: Dict[str, Any] = dict(self._todo_tool_executor.get_handlers())

        def _merge_handlers(next_handlers: Dict[str, Any]) -> None:
            # サイレント上書き防止: 将来 executor が増えたとき同名 tool が
            # 出ると後勝ちで挙動が変わるため、明示的に衝突を検出する。
            overlap = handlers.keys() & next_handlers.keys()
            if overlap:
                raise RuntimeError(
                    f"tool handler name collision in aux stack: {sorted(overlap)}"
                )
            handlers.update(next_handlers)

        if self._memory_recall_tool_executor is not None:
            _merge_handlers(self._memory_recall_tool_executor.get_handlers())
        if self._memory_explore_related_tool_executor is not None:
            _merge_handlers(
                self._memory_explore_related_tool_executor.get_handlers()
            )
        if self._semantic_memory_search_tool_executor is not None:
            _merge_handlers(self._semantic_memory_search_tool_executor.get_handlers())
        # PR-D: recall_by_handle も同じ aux 経路で動かす。
        if self._memory_recall_by_handle_tool_executor is not None:
            _merge_handlers(self._memory_recall_by_handle_tool_executor.get_handlers())
        handler = handlers.get(name)
        if handler is None:
            return LlmCommandResultDto(
                success=False,
                message=f"未対応のツールです: {name}",
                error_code="UNSUPPORTED_TOOL",
            )
        return handler(acting, arguments)

    def _format_active_memos(self, player_id: PlayerId, *, stale_age_ticks: int = 20) -> str:
        """LLM が memo_add で固定した未完了 memo を整形する。空なら ""。

        本家 PromptBuilder と同じロジックを共有するため、active_memos_formatter
        に委譲する (Issue #227 後続レビュー HIGH-2: drift 防止)。
        """
        from ai_rpg_world.application.llm.services.active_memos_formatter import (
            format_active_memos,
        )

        entries = self._todo_store.list_uncompleted(player_id)
        return format_active_memos(
            entries,
            current_tick=self.current_tick(),
            stale_age_ticks=stale_age_ticks,
        )

    # ── 完全プロンプト構築 ──

    # NOTE: objective_text は scenario.metadata.llm_objective_text 駆動に統一。
    # 旧 _ESCAPE_GAME_OBJECTIVE_TEXT (「廃墟から外へ脱出する」) は world_runtime
    # シナリオ専用のハードコードであり、survival_island_v2 のような別シナリオを
    # 走らせても LLM の objective に「廃墟脱出」が出てしまう silent failure を
    # 起こしていた (C run v3: 200 tick 走破中、誰も狼煙台に向かわず物資収集と
    # 廃屋探索に陥った原因)。詳細は docs/memory_system/prefix_cache_v3_deep_analysis.md。
    # consumer 側 (_resolve_scenario_llm_objective_text) で空チェックを行い
    # fail-fast する。fallback も置かない (シナリオごとに勝利条件が違うため)。
    _ESCAPE_GAME_ACTION_INSTRUCTION = (
        "利用可能なツールから、次に取るべき 1 つの行動だけを選んでください。"
    )

    @classmethod
    def escape_game_action_instruction(cls, tool_names: Sequence[str]) -> str:
        """実際の tools payload と一致する auto 用の末尾指示を組み立てる。"""

        available = ", ".join(f'"{name}"' for name in tool_names)
        return (
            f"{cls._ESCAPE_GAME_ACTION_INSTRUCTION}\n"
            f"いま呼べるツール名: {available}\n"
            "文章だけで答えてはなりません。必ず上のツールを 1 つ呼び出してください。"
        )

    def _resolve_scenario_llm_objective_text(self) -> str:
        """``scenario.metadata.llm_objective_text`` を解決し、未設定なら ValueError。

        prompt の objective section に直接埋め込む文。fallback を意図的に持たない:
        - scenario A の objective を scenario B で再利用すると LLM が別ゲームを
          始めてしまう (= cross-scenario silent failure)
        - シナリオ作者に「LLM ゴール文」を明示的に書かせる強制力

        目的層 G6: ``players[].objective`` で全員に個別目的が宣言されている
        シナリオでは「誰も目的を持たない」事態が起きないので、共通目的文が
        空でも許す。逆に 1 人でも欠けていれば従来どおり fail-fast する
        (一部だけ目的があり、残りが無言で目的なしになる静かな失敗を防ぐ)。
        """
        text = (self.scenario.metadata.llm_objective_text or "").strip()
        if not text:
            missing = self._players_missing_objective()
            if missing:
                scenario_id = self.scenario.metadata.id or "<unknown>"
                raise ValueError(
                    f"scenario {scenario_id!r} has empty metadata.llm_objective_text "
                    f"and these players have no players[].objective: {missing}; "
                    "LLM の objective section に埋め込む勝利条件文を scenario JSON の "
                    "metadata.llm_objective_text に追加するか、全プレイヤーに "
                    "players[].objective を書いてください "
                    "(例: \"- 山頂の狼煙台で火を上げ、救助船 (4日目/6日目/7日目) を待つ\")"
                )
        return text

    def _players_missing_objective(self) -> List[str]:
        """``players[].objective`` を持たないプレイヤーの string_id を返す。

        共通目的文が空のときの fail-fast 判定に使う (目的層 G6)。spawn が
        1 人もいないシナリオでは「全員に個別目的がある」とは言えないので、
        番兵を返して従来どおり fail-fast させる。
        """
        spawns = self.scenario.player_spawns
        if not spawns:
            return ["<no player_spawns>"]
        return [
            spawn.string_id
            for spawn in spawns
            if not (spawn.objective or "").strip()
        ]

    def _resolve_player_objective_text(
        self, player_id: PlayerId, scenario_text: str
    ) -> str:
        """目的層 G6: そのプレイヤーの初期目的文を解決する。

        優先順は persona_prompt と揃える: ``players[].objective`` があれば
        それ、無ければシナリオ共通の ``metadata.llm_objective_text``。
        既存シナリオ (全員 objective なし) では常に scenario_text を返すので
        挙動は変わらない。

        spawn が見つからない player_id で呼ばれた場合は共通目的文へ縮退するが、
        黙って他人の目的を渡すことになるので warning を残す。現行の呼び出し元は
        すべて ``get_player_ids()`` (= player_spawns 由来) なので通常は起きない。
        """
        for spawn in self.scenario.player_spawns:
            if spawn.player_id != player_id.value:
                continue
            objective = (spawn.objective or "").strip()
            return objective if objective else scenario_text
        self._warn_unknown_player_spawn(player_id, "objective")
        return scenario_text

    def _warn_unknown_player_spawn(self, player_id: PlayerId, field: str) -> None:
        """player_spawns に無い player_id で目的解決が呼ばれたことを記録する。"""
        logging.getLogger(__name__).warning(
            "player_id=%s is not present in scenario.player_spawns; "
            "falling back to the shared %s. 個別目的が無視されている可能性がある",
            player_id.value,
            field,
        )

    def _resolve_player_goal_locked(self, player_id: PlayerId) -> bool:
        """目的層 G6: そのプレイヤーの初期目的を locked にするかを解決する。

        ``players[].goal_locked`` が明示されていればそれを優先し、未指定なら
        従来どおり ``_scenario_has_goal(self.scenario)`` に従う (挙動不変)。

        spawn が見つからない player_id で呼ばれた場合はシナリオ由来の値へ縮退
        するが、``_resolve_player_objective_text`` と同じ理由で warning を残す。
        """
        for spawn in self.scenario.player_spawns:
            if spawn.player_id != player_id.value:
                continue
            if spawn.goal_locked is not None:
                return spawn.goal_locked
            return _scenario_has_goal(self.scenario)
        self._warn_unknown_player_spawn(player_id, "goal_locked")
        return _scenario_has_goal(self.scenario)

    def _resolve_objective_via_goal_store(
        self, player_id: PlayerId, fallback_text: str
    ) -> str:
        """P5 (目的層 G1): goal store の active 目的を【現在の目的】に描画する。

        遅延 seed: その being にまだ目的が無ければ、シナリオ目的文を
        ``origin=scenario`` で 1 度だけ seed する。描画結果は常に
        ``fallback_text`` と同一 (seed 直後の active はまだ改訂されていない
        ので) = 既存シナリオの挙動不変。store 未構築・being 未解決なら安全に
        fallback_text。

        locked は ``_scenario_has_goal(self.scenario)`` に連動させる
        (HIGH-3 回帰対応)。終了条件のあるシナリオ (win/lose/end や
        player_outcome_rules がある) は locked=True (従来どおり、シナリオの
        終了条件だけが目的の達成/失敗を決める)。勝敗条件を持たない open
        world (persistent_world_demo 等) は locked=False とし、エージェント
        自身が goal_update (言い直し) / goal_outcome (清算) で目的を
        書き換えられるようにする。以前は locked=True を全シナリオに固定して
        いたため、目的文なしの run が作れない (open world も含め全 run が
        必ず何らかの目的文を持つ) ことも重なって、P6 (言い直し) / P8 (清算)
        の実効経路がどのシナリオでも到達不能になっていた。
        """
        store = self._goal_journal_store
        if store is None:
            return fallback_text
        resolver = getattr(self, "_aux_being_resolver", None)
        world_id = getattr(self, "_aux_being_default_world_id", None)
        if resolver is None or world_id is None:
            return fallback_text
        being_id = resolver.resolve_being_id(world_id, player_id)
        if being_id is None:
            return fallback_text
        from ai_rpg_world.domain.memory.goal.value_object.goal_entry import (
            render_current_goal,
        )

        active = store.get_active_by_being(being_id)
        if active is not None:
            return render_current_goal(active)
        # 未 seed: シナリオ目的があれば locked で 1 度だけ積む (P5)。fallback_text は
        # シナリオ目的文なので、seed 後の描画は従来の静的文字列と同一 (挙動不変)。
        # P6: seed する目的が無い (open world) 場合は未定表示になる。
        from uuid import uuid4

        from ai_rpg_world.domain.memory.goal.value_object.goal_entry import (
            GOAL_ORIGIN_SCENARIO,
            GOAL_STATUS_ACTIVE,
            GoalEntry,
        )

        if not fallback_text.strip():
            return render_current_goal(None)
        try:
            tick = self.current_tick()
        except Exception:
            tick = 0
        store.add_by_being(
            being_id,
            GoalEntry(
                goal_id=f"goal-{uuid4().hex}",
                player_id=int(player_id.value),
                text=fallback_text,
                status=GOAL_STATUS_ACTIVE,
                locked=self._resolve_player_goal_locked(player_id),
                origin=GOAL_ORIGIN_SCENARIO,
                created_tick=tick if isinstance(tick, int) else 0,
                created_at=datetime.now(timezone.utc),
            ),
        )
        return render_current_goal(store.get_active_by_being(being_id))

    def _emit_goal_observation(self, player_id: PlayerId, message: str) -> None:
        """P6: 目的まわりの観測 (locked 拒否など) を本人に 1 件届ける。

        goal_update が locked で拒否されたことを silent にせず意識に返すための
        経路 (§4 G2)。food/weather 観測と同じ ``_emit_observation_directly``。
        """
        output = ObservationOutput(
            prose=message,
            structured={"type": "goal_revision"},
            observation_category="self_only",
            schedules_turn=False,
            breaks_movement=False,
        )
        self._emit_observation_directly(player_id, output)

    def _emit_reflect_observation(
        self, player_id: PlayerId, message: str, verdict: str = "stalled"
    ) -> None:
        """P4/P7: 固着パスの reflect (停滞 / 達成 / 乖離の気づき) を「ふと振り返ると

        …」の内省観測として本人に届ける。無意識が感覚を上げ、意識が (P6 の
        goal_update で) 決断する分担。loop_guard 警告と同じ observation buffer
        経路。verdict は種別として structured に載せる (達成の気づきを P6 の
        見直しや P8 の清算が拾えるようにする)。ここでは goal store には触れない。
        """
        output = ObservationOutput(
            prose=message,
            structured={"type": "goal_reflect", "verdict": verdict},
            observation_category="self_only",
            schedules_turn=False,
            breaks_movement=False,
        )
        self._emit_observation_directly(player_id, output)
        # 案A (band-gated thinking): 停滞 (stalled/misaligned) の気づきが実際に
        # 注入された「その場」で熟考ラッチを arm する。cap を通った注入だけが
        # ここに来るので、鼓動 (stall_min_interval) をそのまま熟考の間引きに
        # 流用できる。次行動の run_phase_a が band==strong を条件に consume する。
        # achieved (前進) では焚かない。latch が無い (flag OFF) ときは no-op。
        latch = getattr(self, "_stagnation_reasoning_latch", None)
        if latch is not None and verdict in ("stalled", "misaligned"):
            latch.arm(player_id)

    def _resolve_stagnation_band_value(self, player_id: PlayerId) -> str:
        """player の停滞感カウンタ → band を best-effort で解決する (案A 用)。

        store / being resolver / being が欠けるときは none に縮退する
        (熟考しない = 安全側)。表出側の closure と役割は同じだが、行動経路の
        consumer が別なので小さなヘルパとして独立させる。
        """
        from ai_rpg_world.domain.memory.goal.service.stagnation_pressure_band import (
            STAGNATION_PRESSURE_BAND_NONE,
            resolve_stagnation_pressure_band,
        )

        store = getattr(self, "_stagnation_pressure_store", None)
        resolver = getattr(self, "_aux_being_resolver", None)
        world_id = getattr(self, "_aux_being_default_world_id", None)
        if store is None or resolver is None or world_id is None:
            return STAGNATION_PRESSURE_BAND_NONE
        being_id = resolver.resolve_being_id(world_id, player_id)
        if being_id is None:
            return STAGNATION_PRESSURE_BAND_NONE
        return resolve_stagnation_pressure_band(store.get_by_being(being_id))

    def resolve_turn_reasoning_effort(self, player_id: PlayerId) -> Optional[str]:
        """案A: この行動で reasoning (熟考) を焚くべきか判断し effort or None を返す。

        敵対的レビュー HIGH 2 対応: ここは**決定のみ**で、ラッチの消費も trace も
        しない (副作用は invoke 成功後の ``commit_turn_reasoning_engaged`` に寄せる)。
        停滞ラッチを peek し (= 「停滞注入直後の 1 行動」判定)、band==strong のとき
        だけ effort を返す。band が strong 未満なら焚かないので、古いラッチをここで
        畳んで残さない (「注入直後の 1 行動」の意味を保つ)。flag OFF (ラッチ未構築)
        のときは何もせず None。

        invoke が失敗して commit されなかった場合、strong のラッチは armed のまま
        残るため次行動で再挑戦でき、熟考機会を焼失させない。
        """
        latch = getattr(self, "_stagnation_reasoning_latch", None)
        if latch is None:
            return None
        if not latch.is_armed(player_id):
            return None
        from ai_rpg_world.domain.memory.goal.service.stagnation_reasoning_policy import (
            resolve_stagnation_reasoning_effort,
        )

        band = self._resolve_stagnation_band_value(player_id)
        effort = resolve_stagnation_reasoning_effort(band, fresh_reflect=True)
        if effort is None:
            # band < strong: 焚かないので古いフラグをここで畳む (次行動に持ち越さない)。
            latch.consume(player_id)
        return effort

    def commit_turn_reasoning_engaged(
        self, player_id: PlayerId, effort: str
    ) -> None:
        """案A: 熟考付き行動 (invoke) が成立した後に呼ぶ。ラッチを消費し
        ``AGENT_REASONING_ENGAGED`` trace を 1 件残す。

        敵対的レビュー HIGH 2 対応: ラッチ消費と trace を invoke 成功後まで遅らせる
        ことで、(1) invoke 失敗時に熟考の一発権を焼失させず、(2) trace の意味を
        「実際に行動選択へ投入された熟考」に一致させる (tool-calling 経路では思考
        本文は返らないので、同 tick の LLM metrics の reasoning_tokens と突き合わせて
        「どれだけ熟考したか」を見る)。
        """
        latch = getattr(self, "_stagnation_reasoning_latch", None)
        if latch is None:
            return
        # 防御: ラッチが立っていなければ (= 既に消費済み / 経路不整合) trace を
        # 出さない。二重 commit や想定外の呼び出しで「熟考していないのに engaged」
        # の偽陽性を出さないためのガード。通常経路では resolve が effort を返した
        # 直後に呼ばれるので armed のはず。
        if not latch.consume(player_id):
            return
        band = self._resolve_stagnation_band_value(player_id)
        self._emit_agent_reasoning_engaged_trace(player_id, band, effort)

    def abandon_turn_reasoning(self, player_id: PlayerId) -> None:
        """案A 餓死ループ修正: 熟考ターンの invoke が失敗 (例外 / tool_call なし)
        したときに呼ぶ。熟考の一発権 (latch) を消費して「同条件での再試行」を止める。

        これをしないと、詰まった (band=strong) agent の熟考リクエストが失敗し続ける
        たびに latch が armed のまま残り、毎行動 same-condition で失敗を繰り返して
        餓死する (実 run v3coop_stagnation_002 で P3 が tick42 以降 38 連続失敗)。
        reasoning は実行成立していないので AGENT_REASONING_ENGAGED trace は出さない。
        """
        latch = getattr(self, "_stagnation_reasoning_latch", None)
        if latch is None:
            return
        latch.consume(player_id)

    def _emit_agent_reasoning_engaged_trace(
        self, player_id: PlayerId, band: str, effort: str
    ) -> None:
        """案A: 熟考を焚いた事実 (いつ・なぜ) を trace に残す。recorder 不在なら no-op。"""
        recorder = getattr(self, "_trace_recorder", None)
        if recorder is None:
            return
        being_id_value: Optional[str] = None
        resolver = getattr(self, "_aux_being_resolver", None)
        world_id = getattr(self, "_aux_being_default_world_id", None)
        if resolver is not None and world_id is not None:
            being_id = resolver.resolve_being_id(world_id, player_id)
            if being_id is not None:
                being_id_value = being_id.value
        try:
            from ai_rpg_world.application.trace.events import TraceEventKind

            recorder.record(
                TraceEventKind.AGENT_REASONING_ENGAGED,
                tick=self.current_tick(),
                player_id=player_id.value,
                being_id=being_id_value,
                band=band,
                effort=effort,
                trigger="fresh_reflect",
            )
        except Exception:
            # 敵対的レビュー LOW: これは実験の効果測定用 trace なので、記録失敗を
            # debug で握ると穴が見えにくい。turn は壊さないが warning で気づける
            # ようにする。
            logger.warning(
                "AGENT_REASONING_ENGAGED trace record failed for player_id=%s; skipping",
                player_id.value,
                exc_info=True,
            )

    def _reflect_objective_provider(self, player_id: PlayerId) -> Optional[str]:
        """P4/P7: reflect の監査対象となる現在の目的文を返す (best-effort、

        読み取りのみ)。監査対象は goal store の active 目的に一本化する: active が
        あればその文 (シナリオ目的が locked で seed 済み、または P6 で本人が
        立て直した自己目的)。まだ active が無い場合のみシナリオ目的文へ縮退する
        が、これは seed される内容と同一なので監査対象は変わらない。どちらも
        解決できなければ None (目的が無ければ reflect は判断しない)。この経路は
        副作用 (seed) を起こさない — seed は 【現在の目的】描画側が担う。
        """
        store = self._goal_journal_store
        if store is not None:
            resolver = getattr(self, "_aux_being_resolver", None)
            world_id = getattr(self, "_aux_being_default_world_id", None)
            if resolver is not None and world_id is not None:
                being_id = resolver.resolve_being_id(world_id, player_id)
                if being_id is not None:
                    active = store.get_active_by_being(being_id)
                    if active is not None:
                        return active.text
        try:
            # 目的層 G6: 縮退先も player ごとに解決する。ここが共通文のままだと、
            # 個別目的を持つプレイヤーが seed 前に「他人の目的」で監査される。
            return self._resolve_player_objective_text(
                player_id, self._resolve_scenario_llm_objective_text()
            )
        except Exception:
            return None

    def apply_goal_update_if_present(
        self, player_id: PlayerId, arguments: Dict[str, Any]
    ) -> None:
        """P6/P8: world-action tool の引数の goal_update / goal_outcome を反映する。

        orchestrator (runtime_manager の run_phase_b) が tool 実行後に呼ぶ。
        GOAL_REVISION_ENABLED OFF / goal store 無し / どちらも空なら no-op
        (= 導入前と挙動一致)。being 未解決も no-op。goal_update は立て直し、
        goal_outcome (achieved / abandoned) は清算 (P8)。
        """
        applier = self._goal_revision_applier
        if applier is None:
            return
        if not isinstance(arguments, dict):
            return
        goal_update = arguments.get("goal_update")
        goal_outcome = arguments.get("goal_outcome")
        has_update = isinstance(goal_update, str) and bool(goal_update.strip())
        has_outcome = goal_outcome in (GOAL_OUTCOME_ACHIEVED, GOAL_OUTCOME_ABANDONED)
        if not has_update and not has_outcome:
            return
        resolver = getattr(self, "_aux_being_resolver", None)
        world_id = getattr(self, "_aux_being_default_world_id", None)
        if resolver is None or world_id is None:
            return
        being_id = resolver.resolve_being_id(world_id, player_id)
        if being_id is None:
            return
        try:
            applier.apply(
                being_id,
                player_id,
                goal_update_text=goal_update if has_update else None,
                goal_outcome=goal_outcome if has_outcome else None,
            )
        except Exception:
            logger.exception(
                "apply_goal_update_if_present failed for player_id=%s",
                player_id.value,
            )

    # Issue #227 後続 HIGH-3 改善: stateless formatter / strategy を class-level
    # に持ち、build_full_prompt の毎回 new を避ける + 本家 DefaultPromptBuilder と
    # 同じインスタンスタイプを使うことを明示する。
    _recent_events_formatter: ClassVar[DefaultRecentEventsFormatter] = (
        DefaultRecentEventsFormatter()
    )
    # PR #445: _context_strategy は env (PROMPT_SECTION_ORDER) を尊重するため
    # **instance field に格上げ**。ClassVar の hard-coded default だと
    # run_scenario_experiment が env を読んで run_start trace に書くのに、
    # 実体は無視するという 3 つ目の config-init split silent failure を起こす。
    # PR #438 の Run A (legacy) はこの bug で実際は stable_to_volatile で
    # 動いていた可能性が高い。create_world_runtime 末尾で env から作って
    # 注入する。
    _context_strategy: SectionBasedContextFormatStrategy = field(
        default_factory=SectionBasedContextFormatStrategy
    )

    def _get_or_build_default_prompt_builder(self) -> "DefaultPromptBuilder":
        """本家 DefaultPromptBuilder のインスタンスを lazy 構築してキャッシュする。

        Issue #227 後続 HIGH-3 Part 2: world_runtime の prompt 組み立てを
        DefaultPromptBuilder に統合するため、必要な adapter を集めて 1 回だけ
        構築する。
        """
        cached = getattr(self, "_cached_default_prompt_builder", None)
        if cached is not None:
            return cached

        from ai_rpg_world.application.llm.services.prompt_builder import (
            DefaultPromptBuilder,
        )
        from ai_rpg_world.application.llm.services.prompt_builder_config import (
            EpisodicRecallConfig,
            PromptBuilderCoreServices,
            PromptLimits,
            PromptSectionProviders,
        )
        from ai_rpg_world.application.world_runtime.default_prompt_builder_adapters import (
            WorldAvailableToolsProvider,
            WorldProfileRepositoryAdapter,
            WorldSystemPromptBuilder,
            WorldRuntimeQueryAdapter,
        )

        core = PromptBuilderCoreServices(
            observation_buffer=self._obs_buffer,
            short_term_memory=self._short_term_memory,
            action_result_store=self._action_result_store,
            recent_event_store=self._recent_event_store,
            world_query_service=WorldRuntimeQueryAdapter(self),
            player_profile_repository=WorldProfileRepositoryAdapter(self),
            current_state_formatter=self._formatter,
            recent_events_formatter=self._recent_events_formatter,
            context_format_strategy=self._context_strategy,
            system_prompt_builder=WorldSystemPromptBuilder(self),
            available_tools_provider=WorldAvailableToolsProvider(),
        )
        # objective_text は scenario.metadata.llm_objective_text を 1 度だけ解決する。
        # 空のとき ValueError が立つので、prompt builder 構築時点で fail-fast。
        # lambda 内で resolve すると毎ターン呼ばれて重複ログ + 同一例外を投げる
        # ことになるため、ここで closure キャプチャする。
        resolved_objective_text = self._resolve_scenario_llm_objective_text()
        # P5 (目的層 G1): 常に goal-aware provider を差し込む。goal store が未構築
        # (GOAL_STORE_ENABLED OFF = self._goal_journal_store is None) のとき
        # _resolve_objective_via_goal_store は静的シナリオ文字列をそのまま返す
        # (= 挙動不変)。store 構築 (flag 解決) は create_world_runtime のメモリ
        # 配線側で行い、ここでは provider 設置だけ (prompt builder 構築が LLM
        # 有効時にしか走らないため、store 構築をここに置くと flag が効かない)。
        sections = PromptSectionProviders(
            # 目的層 G6: fallback は player ごとに解決する。players[].objective が
            # あればその人だけ別の目的文で seed され、無ければ従来どおり
            # シナリオ共通文になる。
            objective_text_provider=lambda pid: self._resolve_objective_via_goal_store(
                pid, self._resolve_player_objective_text(pid, resolved_objective_text)
            ),
            memo_store=self._todo_store if self._memo_tools_enabled() else None,
        )
        limits = PromptLimits(
            tile_map_enabled=False,
            default_action_instruction=self._ESCAPE_GAME_ACTION_INSTRUCTION,
        )
        # Issue #283 後続: episodic stack が注入されていれば、prompt builder の
        # passive_recall + noun_matcher を有効化する。未注入なら従来挙動
        # (recall section が出ない)。
        episodic_config = EpisodicRecallConfig()
        if self._episodic_stack is not None:
            # #526 後続: stack に semantic passive recall があれば
            # 【関連する学び】section を出すために渡す (default OFF では None/0)。
            # U3: stack に reinterpretation (段1) があれば、想起時に journal を覗いて
            # 再解釈後テキストで recall を上書きし、想起 episode を recall_buffer に
            # 積む配線を有効化する (default OFF では全 None で従来挙動)。
            _reinterp_coord = self._episodic_stack.reinterpretation_coordinator
            episodic_config = EpisodicRecallConfig(
                passive_recall=self._episodic_stack.passive_recall,
                noun_matcher=self._episodic_stack.noun_matcher,
                # 想起→強化 (recall_count 加算 / CO_RECALL / ヘブ則) の配線。
                # これが無いと想起されても recall_count が 0 のままで、semantic
                # 昇格ゲート (recall_count>=3) を永遠に超えられない
                # (memory_full_002 実験で発覚)。
                memory_link_service=self._episodic_stack.link_service,
                semantic_passive_recall=self._episodic_stack.semantic_passive_recall,
                semantic_passive_top_k=self._episodic_stack.semantic_passive_top_k,
                recall_buffer_store=self._episodic_stack.recall_buffer_store,
                reinterpretation_journal_store=self._episodic_stack.reinterpretation_journal,
                turn_index_provider=(
                    _reinterp_coord.current_turn_index
                    if _reinterp_coord is not None
                    else None
                ),
                # #526 段階 2: 慣化 sidecar。stack で enable された時のみ非 None。
                recall_habituation_store=self._episodic_stack.recall_habituation_store,
                recall_habituation_decay_window_ticks=(
                    self._episodic_stack.recall_habituation_decay_window_ticks
                ),
                # #526 段階 3: 想起スロット sidecar。stack で enable された
                # 時のみ非 None。retrieve 側にも別注入されている (同 store)。
                recall_slot_store=self._episodic_stack.recall_slot_store,
                recall_slot_cooldown_ticks=(
                    self._episodic_stack.recall_slot_cooldown_ticks
                ),
                # #526 段階 3 PR-C: afterglow store。stack で enable された
                # 時のみ非 None。retrieve 側にも同一 store が注入されている。
                afterglow_store=self._episodic_stack.afterglow_store,
                # U10a (予測誤差統一設計 部品6・pending prediction): stack で
                # enable された時のみ非 None。書込みは chunk_coordinator /
                # scheduler 側 (build_episodic_stack / 上の wiring 参照)。
                pending_prediction_store=self._episodic_stack.pending_prediction_store,
            )
        builder = DefaultPromptBuilder(
            core,
            sections=sections,
            limits=limits,
            episodic=episodic_config,
            ui_context_builder=self._ui_context_builder,
            current_tick_provider=lambda: self.current_tick(),
            # Issue #283 後続: recall trace を可視化するため、trace_recorder を
            # provider 経由で渡す (set_trace_recorder で後から差し込まれる)。
            trace_recorder_provider=lambda: self._trace_recorder,
            # presentation 層で先に組まれている loop_guard (record_and_check の
            # 呼び出し主) を peek_streak 用にも共有する。``None`` のままなら
            # instruction 末尾の警告 prefix は出ない。
            tool_call_loop_guard=getattr(
                self, "_injected_tool_call_loop_guard", None
            ),
            # 予測誤差統一設計 U1: _record_action_result の ActionResultRecorder
            # と同じ ledger instance を共有し、この builder が発行した
            # prediction_context_id を consume できるようにする。
            prediction_context_ledger=self._get_prediction_context_ledger(),
        )
        self._cached_default_prompt_builder = builder
        return builder

    def build_full_prompt(
        self,
        player_id: PlayerId,
        *,
        action_instruction: Optional[str] = None,
    ) -> dict:
        """各プレイヤーが LLM ターンで実際に受け取る完全なプロンプトを構築する。

        Issue #227 後続 HIGH-3 Part 2: 本家 DefaultPromptBuilder.build() に統合した。
        section 組み立て・recent_events・active_memos・tile-map field 制御は
        DefaultPromptBuilder 内部で処理される。world_runtime 固有の部分は adapter
        (default_prompt_builder_adapters.py) 経由で注入する:
        - WorldQuery 相当: build_llm_context + _build_minimal_player_state_dto
        - system_prompt: precomputed _world_llm_system_prompt
        - objective/inventory section: provider 経由

        return shape:
            {
                "messages": [
                    {"role": "system", "content": ...},
                    {"role": "user", "content": ...},
                ],
                "tools": [<tool name str>, ...],     # world_runtime は名前 list
                "tool_runtime_context": ToolRuntimeContextDto,
            }

        Issue #227 後続 Step B: 旧 {"system", "user"} flat shape を廃止し
        DefaultPromptBuilder と同じ messages 配列形式に統一 (経路統一の最終仕上げ)。
        旧 shape を期待する caller は messages[0]["content"] / messages[1]["content"]
        への参照に書き換える必要がある。
        """
        self._wire_auxiliary_tool_stack()
        # observation buffer の drain は DefaultPromptBuilder.build() 内で行われる

        tail_sections = tuple(
            section
            for section in (
                self._format_ongoing_conditions(),
                self._format_time_since_last_gathering(),
            )
            if section
        )
        if tail_sections:
            tail_instruction = (
                action_instruction or self._ESCAPE_GAME_ACTION_INSTRUCTION
            )
            action_instruction = "\n\n".join((*tail_sections, tail_instruction))

        builder = self._get_or_build_default_prompt_builder()
        acting = self._acting_being_for(player_id)
        if acting is None:
            raise RuntimeError("Being is not attached to this player.")
        result = builder.build(acting, action_instruction=action_instruction)

        # tool_runtime_context は world_runtime 独自の build_llm_context 経由で取得
        ctx = self.build_llm_context(player_id)

        return {
            "messages": result["messages"],
            "tools": [
                d.name for d in self.get_tool_definitions(player_id=player_id)
            ],
            "tool_runtime_context": ctx.tool_runtime_context,
            # U1: このターンに発行された prediction_context_id をそのまま
            # 露出する (実際の consume は _record_action_result → ledger 経由
            # で player_id をキーに行われるため、呼び出し側がこの値を渡す
            # 必要は無いが、後続 PR のデバッグ・trace 突き合わせ用に残す)。
            "prediction_context_id": result.get("prediction_context_id"),
        }

    def _format_ongoing_conditions(self) -> str:
        """成立中の異常だけを、最終指示の直前へ置ける本文に整形する。"""
        active_flags = self._world_flag_state.as_frozen_set()
        messages = [
            condition.message
            for condition in self.scenario.ongoing_conditions
            if condition.flag in active_flags
        ]
        if not messages:
            return ""
        return "\n".join(
            ["【進行中の異常】", *(f"- {message}" for message in messages)]
        )

    def _format_time_since_last_gathering(self) -> str:
        """自由時間なら、直近の集合からの経過を世界の分数で返す。

        会議後の ``FREE_ROAM.started_at_tick`` は会議終了 tick なので、その
        区間の開始を経過の起点にする。初期区間だけ ``trigger`` が ``None``
        であり、存在しない「前回の集合」を捏造せず run 開始からの経過だと
        言い分けられる。会議中は、いま全員が集まっているため節ごと省く。
        """
        if not self._meeting_enabled or self._game_phase_store.is_meeting():
            return ""
        phase = self._game_phase_store.current
        elapsed_ticks = max(0, int(self.current_tick()) - phase.started_at_tick)
        minutes = elapsed_ticks * (_minutes_per_tick(self.scenario) or 1)
        if phase.trigger is None:
            message = f"ここでの行動が始まってから {minutes} 分が過ぎている。"
        else:
            message = f"最後に全員が集まってから {minutes} 分が過ぎている。"
        return f"【時間の経過】\n- {message}"

    # ── アクション実行 ──

    def _object_display_name_at_player_spot(
        self, player_id: PlayerId, object_str_id: str,
    ) -> str:
        try:
            obj_int = self.id_mapper.get_int("object", object_str_id)
            oid = SpotObjectId.create(obj_int)
            graph = self._spot_graph_repo.find_graph()
            spot_id_text = self.get_player_spot_id(player_id)
            if spot_id_text is None:
                return object_str_id
            spot_id = SpotId.create(int(spot_id_text))
            interior = self._spot_interior_repo.find_by_spot_id(spot_id)
            if interior is None:
                return object_str_id
            obj = interior.get_object(oid)
            if obj is None:
                return object_str_id
            return obj.name.strip() or object_str_id
        except Exception:
            return object_str_id

    def do_interact(
        self, player_id: PlayerId, object_str_id: str, action_name: str,
        *,
        interaction_parameters: Optional[Dict[str, Any]] = None,
        identifier_arguments: Optional[Mapping[str, str]] = None,
        free_text_argument_names: tuple[str, ...] = (),
        inner_thought: Optional[str] = None,
        expected_result: Optional[str] = None,
        intention: Optional[str] = None,
        emotion_hint: Optional[str] = None,
    ) -> SpotInteractionResultDto:
        obj_int = self.id_mapper.get_int("object", object_str_id)
        obj_id = SpotObjectId.create(obj_int)
        obj_label = self._object_display_name_at_player_spot(player_id, object_str_id)
        # NOTE: graph / entity_id / spot_id / display_label /
        # witness_observation_message をここで引き直していたが、それらは 2 件目の
        # SpotObjectInteractedEvent を組み立てるためだけに使われていた。その発火は
        # 下記 NOTE のとおり削除したので、引き直しも不要になった (canonical な
        # 解決は SpotInteractionApplicationService 側が行う)。obj_label は
        # _record_action_result 用なので残し、行動表示は実行結果から受け取る。
        # 備蓄プール (OBJECT_STOCK_AT_LEAST / CONSUME_OBJECT_STOCK) の lazy 再生は
        # 現在 tick が無いと働かない。LLM の採取主経路 (spot_graph_interact →
        # do_interact) はここを通るので、current_tick を必ず渡す。渡し忘れると
        # 採取源が再生せず永久枯渇する (reactive_binding も pool 化で削除済み)。
        from ai_rpg_world.domain.common.value_object import WorldTick
        result = self._interaction_service.execute_interaction(
            player_id, obj_id, action_name,
            interaction_parameters=interaction_parameters,
            current_tick=WorldTick(self.current_tick()),
        )
        action_display_label = result.action_display_label
        result_text = "; ".join(result.messages) if result.messages else "完了"
        # NOTE: ここで SpotObjectInteractedEvent を積んではいけない。
        # `SpotInteractionApplicationService.execute_interaction` が既に同じ
        # event を **witness_policy つきで** 組み立てて publish している
        # (event_publisher は create_world_runtime で無条件に注入される)。
        # かつてはここでも 2 件目を積んでいたが、その event は witness_policy を
        # 渡しておらず既定の SAME_SPOT になるため、
        #   - ACTOR_ONLY を宣言した interaction が同スポットの第三者に漏れる
        #     (= 秘匿行為が成立しない)
        #   - SAME_SPOT の interaction では同じ観測が 2 件届く (= 目撃の水増し)
        # という 2 つの破綻を起こしていた。回帰は
        # tests/demos/test_world_runtime_interact_witness_policy.py が固定する。
        self._process_graph_events()
        self._evaluate_distant_cue_appearances()
        # SpotInteractionResultDto は現状 success フラグを持たない (messages から
        # しか判定できない)。fail 検出経路がドメイン側に出来るまで暫定で True 固定。
        fallback_identifiers, fallback_free_text_names = (
            project_action_arguments_for_history(
                {
                    "target_label": obj_label,
                    "action_name": action_name,
                    **(
                        {"parameters": interaction_parameters}
                        if interaction_parameters is not None
                        else {}
                    ),
                }
            )
        )
        self._record_action_result(
            player_id,
            f"「{obj_label}」で{action_display_label}",
            result_text,
            tool_name=TOOL_NAME_SPOT_GRAPH_INTERACT,
            identifier_arguments=(
                identifier_arguments
                if identifier_arguments is not None
                else fallback_identifiers
            ),
            free_text_argument_names=(
                free_text_argument_names
                if identifier_arguments is not None
                else fallback_free_text_names
            ),
            inner_thought=inner_thought,
            expected_result=expected_result,
            intention=intention,
            emotion_hint=emotion_hint,
        )
        return result

    def do_interact_with_item(
        self,
        player_id: PlayerId,
        item_spec_id: ItemSpecId,
        action_name: str,
        *,
        interaction_parameters: Optional[Dict[str, Any]] = None,
        identifier_arguments: Optional[Mapping[str, str]] = None,
        free_text_argument_names: tuple[str, ...] = (),
        inner_thought: Optional[str] = None,
        expected_result: Optional[str] = None,
        intention: Optional[str] = None,
        emotion_hint: Optional[str] = None,
    ) -> SpotInteractionResultDto:
        """手元の道具に宣言された操作を実行し、通常の interact として記録する。"""
        from ai_rpg_world.domain.common.value_object import WorldTick

        item_def = self._item_spec_repo.find_by_id(item_spec_id)
        item_label = item_def.name if item_def is not None else str(item_spec_id.value)
        result = self._interaction_service.execute_item_interaction(
            player_id,
            item_spec_id,
            action_name,
            interaction_parameters=interaction_parameters,
            current_tick=WorldTick(self.current_tick()),
        )
        self._process_graph_events()
        fallback_identifiers, fallback_free_text_names = (
            project_action_arguments_for_history(
                {
                    "target_label": item_label,
                    "action_name": action_name,
                    **(
                        {"parameters": interaction_parameters}
                        if interaction_parameters is not None
                        else {}
                    ),
                }
            )
        )
        self._record_action_result(
            player_id,
            f"「{item_label}」で{result.action_display_label}",
            "; ".join(result.messages) if result.messages else "完了",
            tool_name=TOOL_NAME_SPOT_GRAPH_INTERACT,
            identifier_arguments=(
                identifier_arguments
                if identifier_arguments is not None
                else fallback_identifiers
            ),
            free_text_argument_names=(
                free_text_argument_names
                if identifier_arguments is not None
                else fallback_free_text_names
            ),
            inner_thought=inner_thought,
            expected_result=expected_result,
            intention=intention,
            emotion_hint=emotion_hint,
        )
        return result

    # ── フェーズ遷移 (会議と投票) ──

    def eligible_voters(self) -> List[PlayerId]:
        """投票できる player。行動可能な生存者だけ。

        退場した相手 (DEAD / EJECTED) と倒れている相手を外す。倒れている
        相手は観測が届かないので投票する機会が無く、母数に残すと**永久に
        待つ**ことになる。過半数の計算も狂い、「誰も追放できない」が
        「同点で追放なし」と区別できなくなる (設計 doc H-1)。
        """
        voters: List[PlayerId] = []
        for pid in self.get_player_ids():
            if not self._player_life_query.can_vote(pid):
                continue
            voters.append(pid)
        return voters

    def cast_vote(self, voter_player_id: PlayerId, target_player_id=None):
        """会議で 1 票を投じる。``target_player_id`` が None なら棄権。

        全員が投じ終えたら、その場で集計して会議を閉じる。

        会議中でなければ拒否する。toolset から外すだけでは、悪性クライアント
        や provider の変換崩れで届く可能性がある (設計 doc H-6)。
        """
        service = self._meeting_command_service
        if service is None:
            raise RuntimeError("MeetingCommandService is not wired")
        return service.cast_vote(voter_player_id, target_player_id)

    def eject_player(self, player_id: PlayerId) -> bool:
        """投票の結果として player を追放する。

        outcome を EJECTED で確定させる。DEAD と分けるのは、分析で
        「殺されたのか追放されたのか」を読み分けたいのと、陣営の勝敗条件が
        両者を同じ「退場」として数える必要があるため (どちらも
        ``is_eliminated`` が True)。

        集計と投票そのものは PR 6。ここは確定させる口だけを用意する
        (届かない enum メンバを残さないため、この PR で実行経路まで通す)。
        """
        from ai_rpg_world.domain.player.enum.player_outcome_enum import (
            PlayerOutcomeEnum,
        )

        registry = self._player_outcome_registry
        if registry is None:
            return False
        if not registry.set_outcome(player_id, PlayerOutcomeEnum.EJECTED):
            return False
        # 追放された者はその場から居なくなる。
        #
        # **キルとは違う。** 殺された者の死体はその場に残り、見つけた人が
        # 通報できる。追放は全員の前で行われ、結果も全員に届いているので、
        # 死体を残す理由が無い。残すと同席者行に出続け、漁る・襲うといった
        # 「必ず失敗する手」の対象になる (実 run で実際にそう出ていた)。
        try:
            graph = self._spot_graph_repo.find_graph()
            graph.unplace_entity(EntityId.create(int(player_id)))
            self._spot_graph_repo.save(graph)
        except Exception:
            # 追放そのものは outcome で確定済み。配置の後始末に失敗しても
            # 追放を取り消さない。ただし黙って進むと「追放したのに居る」
            # 状態に気付けないので記録は残す。
            logger.warning(
                "追放した player を graph から外せなかった player_id=%s",
                int(player_id),
                exc_info=True,
            )
        return True

    def call_emergency_meeting(
        self,
        player_id: PlayerId,
        *,
        trigger: str = MeetingStartTrigger.EMERGENCY_BUTTON.value,
    ):
        """専用の会議commandへ緊急招集を委譲する。"""
        service = self._meeting_command_service
        if service is None:
            raise RuntimeError("MeetingCommandService is not wired")
        return service.call_emergency_meeting(player_id, trigger=trigger)

    def report_body(self, reporter_player_id: PlayerId, target_player_id: PlayerId):
        """専用の会議commandへ死体報告を委譲する。"""
        service = self._meeting_command_service
        if service is None:
            raise RuntimeError("MeetingCommandService is not wired")
        return service.report_body(reporter_player_id, target_player_id)

    def begin_meeting(
        self,
        *,
        initiator_player_id: Optional[PlayerId] = None,
        trigger: str = MeetingStartTrigger.EMERGENCY_BUTTON.value,
    ):
        """会議を始め、全員に観測として配る。

        store の更新と event の publish を 1 か所に閉じる。片方だけ行うと
        「世界は会議中なのに誰もそれを知らない」「観測は届いたのに世界は
        自由時間のまま」のどちらかになる。

        既に会議中なら ``GamePhaseTransitionException`` を投げ、**状態も
        観測も動かさない**。1 tick 内で 2 人が緊急ボタンを押すのは実際に
        起こりうるので、2 人目のぶんまで配ると同じ会議が二度始まったように
        読める。
        """
        state = self._transition_phase(
            lambda tick: self._game_phase_store.begin_meeting(
                tick=tick,
                trigger=trigger,
                initiator_player_id=(
                    int(initiator_player_id)
                    if initiator_player_id is not None
                    else None
                ),
            ),
            trigger=trigger,
            initiator_player_id=initiator_player_id,
            after_apply=self._resolve_ongoing_conditions_on_meeting_start,
        )
        self._record_meeting_started(state)
        return state

    def _resolve_ongoing_conditions_on_meeting_start(self) -> None:
        """成立中の異常だけを、シナリオが明示した効果で解決する。

        ``on_meeting_start`` の有無が、会議で解ける異常の唯一の宣言である。
        同期操作の効果を名前で探す暗黙の結合は作らない。会議遷移が拒否された
        ときに異常だけ解けないよう、呼び出し元は遷移成功後の ``after_apply``
        からこの処理を呼ぶ。
        """
        from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior

        active_flags = self._world_flag_state.as_frozen_set()
        conditions = tuple(
            condition
            for condition in self.scenario.ongoing_conditions
            if condition.flag in active_flags and condition.on_meeting_start
        )
        for condition in conditions:
            result = self._effect_service.apply_effects(
                interior=SpotInterior.empty(),
                acting_object=None,
                effects=condition.on_meeting_start,
                world_flags=self._world_flag_state.as_frozen_set(),
            )
            self._world_flag_state.replace_from_interaction(
                result.new_flags,
                context=WorldFlagMutationContext(
                    source=WorldFlagMutationSource.MEETING_RESOLUTION,
                    actor_player_id=None,
                ),
            )
            for message in result.messages:
                self._publish_meeting_condition_resolution(
                    condition.flag,
                    (message,),
                )

    def _publish_meeting_condition_resolution(
        self,
        flag: str,
        messages: tuple[str, ...],
    ) -> None:
        """会議で解決した異常の宣言文を全playerへ確定後に届ける。"""
        for message in messages:
            for player_id in self.get_player_ids():
                self._emit_observation_directly(
                    player_id,
                    ObservationOutput(
                        prose=message,
                        structured={
                            "type": "meeting_condition_resolved",
                            "flag": flag,
                        },
                        observation_category="environment",
                        schedules_turn=True,
                        breaks_movement=False,
                    ),
                )

    def end_meeting(self, *, reason: str = MeetingEndReason.VOTE_CONCLUDED.value):
        """会議を終えて自由時間へ戻し、全員に観測として配る。

        終わったことが届かないと、いつまで発言してよいのか分からない。
        """
        service = self._meeting_command_service
        if service is None:
            raise RuntimeError("MeetingCommandService is not wired")
        return service.end_meeting(reason=reason)

    def _record_meeting_ended(
        self,
        meeting_state: Any,
        state: Any,
        reason: str,
    ) -> None:
        """確定済みの会議終了時間を集計し、traceへ記録する。"""
        _ = state
        meeting_spot_id, meeting_spot_name = self._meeting_location(meeting_state)
        duration = max(0, int(self.current_tick()) - meeting_state.started_at_tick)
        self._cumulative_meeting_ticks += duration
        recorder = self._trace_recorder
        if recorder is not None:
            recorder.record(
                TraceEventKind.MEETING_ENDED,
                tick=int(self.current_tick()),
                started_at_tick=meeting_state.started_at_tick,
                ended_at_tick=int(self.current_tick()),
                trigger=meeting_state.trigger,
                spot_id=meeting_spot_id,
                spot_name=meeting_spot_name,
                end_reason=reason,
                duration_ticks=duration,
                cumulative_meeting_ticks=self._cumulative_meeting_ticks,
            )

    def _record_meeting_started(self, state: Any) -> None:
        """会議が run 終了時点で継続中でも開始地点と契機を失わない。"""
        recorder = self._trace_recorder
        if recorder is None:
            return
        spot_id, spot_name = self._meeting_location(state)
        recorder.record(
            TraceEventKind.MEETING_STARTED,
            tick=state.started_at_tick,
            trigger=state.trigger,
            spot_id=spot_id,
            spot_name=spot_name,
            initiator_player_id=state.initiator_player_id,
        )

    def _meeting_location(self, state: Any) -> tuple[Optional[str], Optional[str]]:
        """集合後も動かない招集者の位置から会議の開催場所を解く。"""
        initiator = state.initiator_player_id
        if initiator is None:
            return None, None
        player_id = PlayerId(int(initiator))
        spot_id = self.get_player_spot_id(player_id)
        if spot_id is None:
            return None, None
        try:
            return spot_id, self.get_player_spot_name(player_id)
        except Exception:
            return spot_id, None

    def _transition_phase(
        self,
        apply: Any,
        *,
        trigger: str,
        initiator_player_id: Optional[PlayerId],
        after_apply: Optional[Callable[[], None]] = None,
    ):
        """遷移を適用して event を publish する。

        遷移が拒否された場合は例外がそのまま抜け、publish には進まない
        (状態が動いていないのに観測だけ配るのを防ぐ)。

        ``after_apply`` は遷移が成功した直後だけ呼ぶ。会議終了時の遺体削除を
        ここへ置くことで、拒否された終了要求が世界状態の一部だけを動かす
        ことを防ぐ。
        """
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
            GamePhaseChangedEvent,
        )

        old_phase = self._game_phase_store.current.phase
        state = apply(int(self.current_tick()))
        if after_apply is not None:
            after_apply()

        who = ""
        if initiator_player_id is not None:
            try:
                who = self.get_player_name(initiator_player_id)
            except Exception:
                who = ""
        if self._speech_event_publisher is not None:
            graph = self._spot_graph_repo.find_graph()
            self._speech_event_publisher.publish_all([
                GamePhaseChangedEvent.create(
                    aggregate_id=graph.graph_id,
                    aggregate_type="SpotGraphAggregate",
                    old_phase=old_phase,
                    new_phase=state.phase,
                    trigger=trigger,
                    initiator_display_name=who,
                )
            ])
        return state

    def available_player_action_names(self, actor_player_id: PlayerId) -> tuple:
        """**その人に見えている**対人 action 名 (シナリオ直下 ``player_interactions``)。

        行為者を必ず受け取る。以前は引数が無く全件を返しており、クルーが
        操作名を打ち間違えると ``strike_down`` の存在が案内から漏れていた。
        """
        svc = getattr(self, "_player_interaction_service", None)
        if svc is None:
            return ()
        status = self._player_status_repo.find_by_id(actor_player_id)
        return svc.available_action_names(
            getattr(status, "state", None),
            actor_player_id=actor_player_id,
        )

    def do_interact_with_player(
        self, actor_player_id: PlayerId, target_player_id: PlayerId, action_name: str,
        *,
        interaction_parameters: Optional[Dict[str, Any]] = None,
        identifier_arguments: Optional[Mapping[str, str]] = None,
        free_text_argument_names: tuple[str, ...] = (),
        inner_thought: Optional[str] = None,
        expected_result: Optional[str] = None,
        intention: Optional[str] = None,
        emotion_hint: Optional[str] = None,
    ):
        """同じ場所にいるプレイヤーを対象にした interaction を実行する。

        ``do_interact`` (物体) と対になる。行為の宣言はシナリオ直下の
        ``player_interactions`` にあり、場所の制約は前提条件で書く
        (docs/memory_system/interpersonal_interaction_design.md §3.2)。
        """
        from ai_rpg_world.domain.common.value_object import WorldTick
        svc = self._player_interaction_service
        result = svc.execute(
            actor_player_id,
            target_player_id,
            action_name,
            interaction_parameters=interaction_parameters,
            current_tick=WorldTick(self.current_tick()),
        )
        self._process_graph_events()
        target_label = next(
            (
                s.name
                for s in self.scenario.player_spawns
                if int(s.player_id) == int(target_player_id)
            ),
            f"プレイヤー({int(target_player_id)})",
        )
        fallback_identifiers, fallback_free_text_names = (
            project_action_arguments_for_history(
                {
                    "target_label": target_label,
                    "action_name": action_name,
                    **(
                        {"parameters": interaction_parameters}
                        if interaction_parameters is not None
                        else {}
                    ),
                }
            )
        )
        self._record_action_result(
            actor_player_id,
            f"「{target_label}」に対して{result.action_display_label}",
            "; ".join(result.messages) if result.messages else "完了",
            tool_name=TOOL_NAME_SPOT_GRAPH_INTERACT,
            identifier_arguments=(
                identifier_arguments
                if identifier_arguments is not None
                else fallback_identifiers
            ),
            free_text_argument_names=(
                free_text_argument_names
                if identifier_arguments is not None
                else fallback_free_text_names
            ),
            inner_thought=inner_thought,
            expected_result=expected_result,
            intention=intention,
            emotion_hint=emotion_hint,
        )
        return result

    def do_drop_item(
        self, player_id: PlayerId, slot_id_value: int,
    ) -> ItemTransferResult:
        """指定スロットのアイテムを現在地に落とす。

        観測パイプライン統合と LLM tool 経路はフォローアップ PR で扱う。
        現状はランナー/テストから直接呼ばれる前提で、結果メッセージを
        action_result_store に追記して履歴に残すまでを行う。
        """
        from ai_rpg_world.domain.player.value_object.slot_id import SlotId
        result = self._item_transfer_service.drop_item(player_id, SlotId(slot_id_value))
        result_text = "; ".join(result.messages) if result.messages else "落とした"
        # ItemTransferResult は現状 success フラグなし (例外は service 側で投げる)。
        # ここまで到達していれば transfer 自体は完了している前提。
        self._record_action_result(
            player_id,
            f"スロット{slot_id_value}のアイテムを地面に置いた",
            result_text,
            tool_name=TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
        )
        return result

    def do_pickup_item(
        self, player_id: PlayerId, item_instance_id_value: int,
    ) -> ItemTransferResult:
        """現在地の地面アイテムを拾う。

        item_instance_id_value はランナー/テストが
        ``list_ground_items_at_player_spot`` で得た id を渡す前提。LLM
        tool では将来ラベル (例: G1, G2) で参照させる予定だがそれは別 PR。
        """
        from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
        result = self._item_transfer_service.pickup_item(
            player_id, ItemInstanceId.create(item_instance_id_value),
        )
        result_text = "; ".join(result.messages) if result.messages else "拾い上げた"
        self._record_action_result(
            player_id,
            f"地面のアイテム#{item_instance_id_value}を拾った",
            result_text,
            tool_name=TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
        )
        return result

    def list_ground_items_at_player_spot(self, player_id: PlayerId) -> tuple:
        """ランナー / テストから現在地の地面アイテム一覧を取り出すヘルパ。"""
        return self._item_transfer_service.list_ground_items_at_player_spot(player_id)

    def do_listen(self, player_id: PlayerId) -> None:
        """「耳を澄ます」: 自 spot + 隣接 spot の環境音観測を投入する。

        ``SpotGraphAggregate.emit_listen_carefully`` で
        環境音と隣接地点の人の気配 event を発火し、観測パイプラインで
        recipient strategy がプレイヤー本人にだけ届ける。

        Note:
            環境音と人の気配は別の observation として配送される。片方の
            件数だけを返すと「0 = 何も聞こえない」と誤読されるため、件数を
            API に残さず実行と配送だけを担う。
        """
        graph = self._spot_graph_repo.find_graph()
        eid = EntityId.create(int(player_id))
        moving_entity_ids = frozenset(
            EntityId.create(int(status.player_id))
            for status in self._player_status_repo.find_all()
            if not status.is_down
        )
        # `add_event` は graph 集約内に積むだけで保存はしない。
        # `_process_graph_events` が `get_events` で取り出して observation
        # pipeline に流す。
        graph.emit_listen_carefully(eid, moving_entity_ids=moving_entity_ids)
        # _process_graph_events 内部で clear するので、ここでは再取得しない。
        self._process_graph_events()

    def do_explore(
        self,
        player_id: PlayerId,
        *,
        identifier_arguments: Optional[Mapping[str, str]] = None,
        free_text_argument_names: tuple[str, ...] = (),
        inner_thought: Optional[str] = None,
        expected_result: Optional[str] = None,
        intention: Optional[str] = None,
        emotion_hint: Optional[str] = None,
    ) -> SpotExplorationResultDto:
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import SpotExploredEvent
        graph = self._spot_graph_repo.find_graph()
        eid = EntityId.create(int(player_id))
        spot_id = graph.get_entity_spot(eid)
        spot_name = self.get_player_spot_name(player_id)
        result = self._exploration_service.explore_once(player_id)
        graph = self._spot_graph_repo.find_graph()
        graph.add_event(SpotExploredEvent.create(
            aggregate_id=graph._graph_id,
            aggregate_type="SpotGraphAggregate",
            entity_id=eid,
            spot_id=spot_id,
            discoveries=result.discovery_descriptions,
        ))
        self._process_graph_events()
        if result.discovery_descriptions:
            result_text = f"新たに分かったこと: {', '.join(result.discovery_descriptions)}"
        else:
            result_text = "目立った発見はなかった"
        self._record_action_result(
            player_id,
            f"「{spot_name}」の周辺を探索した",
            result_text,
            tool_name=TOOL_NAME_SPOT_GRAPH_EXPLORE,
            identifier_arguments=identifier_arguments,
            free_text_argument_names=free_text_argument_names,
            inner_thought=inner_thought,
            expected_result=expected_result,
            intention=intention,
            emotion_hint=emotion_hint,
        )
        return result

    def do_move(
        self,
        player_id: PlayerId,
        dest_spot_str_id: str,
        *,
        identifier_arguments: Optional[Mapping[str, str]] = None,
        free_text_argument_names: tuple[str, ...] = (),
        inner_thought: Optional[str] = None,
        expected_result: Optional[str] = None,
        intention: Optional[str] = None,
        emotion_hint: Optional[str] = None,
    ) -> None:
        """目的地へ向けて移動を開始する (#404 fix: ネスト advance_tick を排除)。

        旧実装: ``start_travel_to_spot`` 後に ``for _ in range(200): advance_tick()``
        を回し、到着するまでツール内で同期的に待っていた。これが driver tick 1 回
        の中で world tick を 70+ も連打 → 各 world tick で heartbeat / LLM
        turn trigger が発火 → 1 driver tick = 656 秒という wall time スパイクと
        「travel 1 回で 134 LLM call」の silent failure を生んでいた (#404)。

        新実装: ``start_travel_to_spot`` で travel state を立てて即 return する。
        以降の world tick は外側の experiment loop が回し、その中の
        ``SpotGraphTravelStageService`` が naturally に 1 tick ずつ travel を
        進める。本人の LLM ターンは ``runtime_manager._can_player_act`` の
        ``is_traveling`` フィルタで sleep し、到着時に travel_stage の
        ``on_arrival`` コールバックで再起床される (= turn_scheduler.schedule_turn)。

        この設計変更により:
        - 1 driver tick = 1 world tick が概ね成立する (heartbeat / other actions
          は通常通り進む)
        - 他プレイヤーは A の移動中も自分の next-turn 規律で動ける
        - tool 結果は 「{X} へ向かって出発した / 移動中」 になる。到着の旨は
          後続 turn で snapshot の current_spot 変化として LLM に届く
        """
        from_name = self.get_player_spot_name(player_id)
        dest_int = self.id_mapper.get_int("spot", dest_spot_str_id)
        dest_sid = SpotId.create(dest_int)
        inv = self._player_inventory_repo.find_by_id(player_id)
        owned: FrozenSet[ItemSpecId] = frozenset()
        if inv:
            owned = collect_owned_item_spec_ids_from_inventory(inv, self._item_repo)
        flags = self._world_flag_state.as_frozen_set()
        # 失敗は同期的に例外で返る (SpotTravelUnreachable / ConnectionNotPassable
        # 等)。tool 層がそれを LlmCommandResultDto に変換する想定なので、
        # ここでは catch せず素通しする。
        self._movement_service.start_travel_to_spot(player_id, dest_sid, owned, flags)

        self._process_graph_events()
        graph_after = self._spot_graph_repo.find_graph()
        dest_name = graph_after.get_spot(dest_sid).name

        # 同一スポット指定の場合 start_travel_to_spot は no-op で travel state を
        # 立てない。その場合は「すでにそこに居る」結果を返す。
        eid = EntityId.create(int(player_id))
        try:
            current_spot = graph_after.get_entity_spot(eid)
        except Exception:
            current_spot = None
        status = self._player_status_repo.find_by_id(player_id)
        nav = status.spot_navigation_state if status is not None else None
        already_there = current_spot == dest_sid and (nav is None or not nav.is_traveling)
        if already_there:
            self._record_action_result(
                player_id,
                f"「{dest_name}」へ移動しようとした",
                f"「{dest_name}」には既に居る",
                tool_name=TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
                identifier_arguments=(
                    identifier_arguments
                    if identifier_arguments is not None
                    else project_action_arguments_for_history(
                        {"destination_label": dest_name}
                    )[0]
                ),
                free_text_argument_names=free_text_argument_names,
                inner_thought=inner_thought,
                expected_result=expected_result,
                intention=intention,
                emotion_hint=emotion_hint,
            )
            return

        # 移動開始の action result を記録する。scene_boundary は「scene を変える
        # 意思決定」の時点で立てる (cognitive science の doorway effect は意図
        # 形成の瞬間 + 物理的境界通過の両方が関係するが、本実装では tool call
        # 時点を chunk 境界として扱う)。start_travel_to_spot が成功している以上
        # 経路は確保されていて、advance_spot_travel_one_tick が異常終了しない
        # 限り必ず arrival する。
        self._record_action_result(
            player_id,
            f"「{from_name}」から「{dest_name}」へ向かって出発した",
            f"「{dest_name}」へ移動中。到着までは他の行動はできない。",
            tool_name=TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            identifier_arguments=(
                identifier_arguments
                if identifier_arguments is not None
                else project_action_arguments_for_history(
                    {"destination_label": dest_name}
                )[0]
            ),
            free_text_argument_names=free_text_argument_names,
            scene_boundary=True,
            inner_thought=inner_thought,
            expected_result=expected_result,
            intention=intention,
            emotion_hint=emotion_hint,
        )

    def do_wait(self, player_id: PlayerId, reason: str = "") -> int:
        """その場で待機する (#471 fix: ネスト advance_tick を排除)。

        旧実装: 内部で ``self.advance_tick()`` を呼んで world tick を 1 進めて
        いた。これが #404 ``do_move`` と同型の再帰カスケードを生んでいた:
        ``advance_tick`` → ``_run_post_tick_hooks`` → ``run_scheduled_turns``
        → 他プレイヤーの LLM ターン → ``spot_graph_wait`` → ``do_wait`` →
        ``advance_tick`` …。driver loop の ``current_tick < MAX_WORLD_TICKS``
        ガードは iteration 先頭でしか効かないため、cascade 中は ``MAX_WORLD_TICKS``
        を黙ってバイパスし、1 driver iteration で +100 tick / 200 LLM call /
        wall 30 分のスパイクが発生していた (#468 L run で観測)。

        新実装: ``do_wait`` は「自分のこのターンは何もしない」という意思決定
        を表すだけで、world tick は進めない。進行は外側 driver loop に任せる。
        返り値は現在 tick (進めていない) を返す互換のため。

        **行動記録はここでは作らない。記録は呼び出し側 (executor) の責務。**
        かつてはここでも ``_record_action_result`` を呼んでいたが、executor が
        返す結果 DTO を他の全ツールと同じようにターン実行が記録するので、
        1 回の wait で行動記録が 2 件できていた。「ツールを実行したら結果が
        1 件記録される」という規約に wait だけ例外を作らないため、こちら側を
        落とした。``reason`` は結果の文面を組むために残している。
        """
        return self.current_tick()

    def _append_scenario_event_observation(self, event: ScenarioEventDef, message: str) -> None:
        # Issue #276 経路二重化解消: 直接 ``_obs_buffer.append`` していた経路を
        # ``_emit_observation_directly`` に統一。これで trace 記録と
        # ``maybe_schedule`` (schedules_turn=True のときの turn 投入) を漏らさ
        # ない。
        recipients = self._scenario_event_recipients(event)
        for player_id in recipients:
            output = ObservationOutput(
                prose=message,
                structured={
                    "type": "scenario_event",
                    "event_id": event.event_id,
                    "message": message,
                },
                observation_category=event.observation_category,  # type: ignore[arg-type]
                schedules_turn=event.schedules_turn,
                breaks_movement=event.breaks_movement,
            )
            self._emit_observation_directly(player_id, output)

    def _append_synchronized_action_observation(
        self,
        group_id: str,
        outcome: str,
        recipient_ids: tuple[int, ...],
        message: str,
    ) -> None:
        """同期操作の結果を、実際に準備へ参加した主体だけへ届ける。

        同期 group 自体は場所を持たないため、非参加者へ世界横断で知らせる
        根拠がない。完成時は全参加者、時間切れ時は部分的に準備した参加者が、
        自分の試みの結果として同じ文を受け取る。
        """
        for raw_player_id in recipient_ids:
            output = ObservationOutput(
                prose=message,
                structured={
                    "type": "synchronized_action_result",
                    "group_id": group_id,
                    "outcome": outcome,
                    "message": message,
                },
                observation_category="self_only",
                schedules_turn=False,
                breaks_movement=False,
            )
            self._emit_observation_directly(PlayerId(raw_player_id), output)

    def _scenario_event_recipients(self, event: ScenarioEventDef) -> List[PlayerId]:
        if event.recipients == "players_at_spot" and event.target_spot_id is not None:
            graph = self._spot_graph_repo.find_graph()
            presence = graph.presence_at(SpotId.create(event.target_spot_id))
            return [PlayerId(int(eid)) for eid in presence.present_entity_ids]
        return self.get_player_ids()

    def _evaluate_distant_cue_appearances(self) -> None:
        """動的遠景 cue の false→true 境界を検出し、見える player へ観測を配る。

        初回評価時点で既に active な cue は baseline として記録するだけで配達しない。
        これにより、シナリオ初期 true や snapshot resume 直後の再発火を防ぐ。
        """
        cues = tuple(getattr(self.scenario, "distant_cues", ()) or ())
        if not cues:
            return
        for cue in cues:
            cue_id = str(getattr(cue, "cue_id", "<unknown>"))
            active = self._is_distant_cue_active(cue)
            if active is None:
                continue
            state = self._distant_cue_states.get(
                cue_id,
                {"active": False, "initialized": False, "last_changed_tick": None},
            )
            initialized_before = bool(state.get("initialized", False))
            old_active = bool(state.get("active", False))
            if not initialized_before:
                self._distant_cue_states[cue_id] = {
                    "active": active,
                    "initialized": True,
                    "last_changed_tick": None,
                }
                continue
            if old_active == active:
                continue
            self._distant_cue_states[cue_id] = {
                "active": active,
                "initialized": True,
                "last_changed_tick": self.current_tick(),
            }
            appear_event = getattr(cue, "appear_event", None)
            if not (active and not old_active and appear_event is not None):
                continue
            deliveries = self._visible_distant_cue_deliveries(cue)
            for player_id, spot_id, visible in deliveries:
                message = self._format_distant_cue_appear_message(
                    str(getattr(appear_event, "message", "")),
                    visible=visible,
                )
                output = ObservationOutput(
                    prose=message,
                    structured={
                        "type": "distant_cue_appeared",
                        "cue_id": cue_id,
                        "visible_name": str(getattr(cue, "visible_name", "")),
                        "origin_area_id": str(getattr(cue, "origin_area_id", "")),
                        "direction": visible.direction,
                        "distance_band": visible.distance_band,
                    },
                    observation_category="environment",
                    schedules_turn=bool(getattr(appear_event, "schedules_turn", False)),
                    breaks_movement=False,
                )
                self._emit_observation_directly(player_id, output)
                self._record_distant_cue_delivered(
                    cue=cue,
                    player_id=player_id,
                    spot_id=spot_id,
                    visible=visible,
                    schedules_turn=output.schedules_turn,
                )
            self._record_distant_cue_state_changed(
                cue=cue,
                old_active=old_active,
                new_active=active,
                initialized_before=initialized_before,
                visible_recipient_count=len(deliveries),
                delivery_skipped_reason=(
                    "no_visible_recipients" if not deliveries else None
                ),
            )

    def _is_distant_cue_active(self, cue: Any) -> Optional[bool]:
        source = getattr(cue, "source", None)
        cue_id = str(getattr(cue, "cue_id", "<unknown>"))
        if source is None or getattr(source, "kind", None) != "object_state":
            logger.warning(
                "distant cue source kind is unsupported at runtime: cue_id=%s",
                cue_id,
            )
            return None
        obj = self._find_distant_cue_source_object(getattr(source, "object_id", None))
        if obj is None:
            logger.warning(
                "distant cue source object is missing: cue_id=%s",
                cue_id,
            )
            self._record_distant_cue_skipped(
                cue=cue,
                reason="cue_source_object_missing",
            )
            return None
        state_key = str(getattr(source, "state_key", ""))
        return obj.state.get(state_key) == getattr(source, "equals", None)

    def _find_distant_cue_source_object(self, object_id: Any) -> Any:
        try:
            if not isinstance(object_id, SpotObjectId):
                object_id = SpotObjectId.create(
                    int(getattr(object_id, "value", object_id))
                )
        except Exception:
            return None
        graph = self._spot_graph_repo.find_graph()
        for node in graph.iter_spot_nodes():
            interior = self._spot_interior_repo.find_by_spot_id(node.spot_id)
            if interior is None:
                continue
            obj = interior.get_object(object_id)
            if obj is not None:
                return obj
        return None

    def _visible_distant_cue_deliveries(
        self,
        cue: Any,
    ) -> list[tuple[PlayerId, SpotId, DistantViewVisibleCandidate]]:
        graph = self._spot_graph_repo.find_graph()
        spots = self._distant_view_spots(graph)
        areas_by_id = {area.area_id: area for area in self._distant_view_areas()}
        origin_area_id = str(getattr(cue, "origin_area_id", ""))
        area = areas_by_id.get(origin_area_id)
        if area is None:
            logger.warning(
                "distant cue origin area is missing: cue_id=%s area_id=%s",
                getattr(cue, "cue_id", "<unknown>"),
                origin_area_id,
            )
            return []
        candidate = DistantViewCandidate(
            candidate_id=str(getattr(cue, "cue_id", "<unknown>")),
            kind="cue",
            visible_name=str(getattr(cue, "visible_name", "")),
            prominence=float(getattr(cue, "prominence", 0.0)),
            x=area.x,
            y=area.y,
            descriptions=dict(getattr(cue, "ambient_descriptions", {}) or {}),
            origin_area_id=origin_area_id,
        )
        service = self._distant_view_service()
        deliveries: list[tuple[PlayerId, SpotId, DistantViewVisibleCandidate]] = []
        for player_id in self.get_player_ids():
            entity_id = EntityId.create(int(player_id))
            try:
                current_spot_id = graph.get_entity_spot(entity_id)
            except Exception:
                continue
            visible = service.evaluate_candidate_visibility(
                current_spot_id=current_spot_id.value,
                spots=spots,
                connections=tuple(
                    DistantViewConnection(
                        from_spot_id=conn.from_spot_id.value,
                        to_spot_id=conn.to_spot_id.value,
                    )
                    for conn in graph.iter_outgoing_connections_from(current_spot_id)
                ),
                candidate=candidate,
            )
            if visible is not None:
                deliveries.append((player_id, current_spot_id, visible))
        return deliveries

    def _distant_view_spots(self, graph: Any) -> tuple[DistantViewSpot, ...]:
        return tuple(
            DistantViewSpot(
                spot_id=node.spot_id.value,
                area_id=node.area_id,
                x=(node.position.x if node.position is not None else None),
                y=(node.position.y if node.position is not None else None),
                is_outdoor=bool(node.is_outdoor),
            )
            for node in graph.iter_spot_nodes()
        )

    def _distant_view_areas(self) -> tuple[DistantViewArea, ...]:
        return tuple(
            DistantViewArea(
                area_id=str(getattr(area, "area_id")),
                name=str(getattr(area, "name", "")),
                visible_name=str(getattr(area, "visible_name", "")),
                prominence=float(getattr(area, "prominence", 0.0)),
                x=getattr(getattr(area, "position", None), "x", None),
                y=getattr(getattr(area, "position", None), "y", None),
                distant_descriptions=dict(
                    getattr(area, "distant_descriptions", {}) or {}
                ),
            )
            for area in getattr(self.scenario, "areas", ())
        )

    def _distant_view_service(self) -> DistantViewService:
        service = getattr(self._state_builder, "_distant_view_service", None)
        return service if isinstance(service, DistantViewService) else DistantViewService()

    def _format_distant_cue_appear_message(
        self,
        template: str,
        *,
        visible: DistantViewVisibleCandidate,
    ) -> str:
        message = template or ""
        replacements = {
            "{direction}": visible.direction,
            "{visible_name}": visible.source.visible_name,
            "{distance_band}": visible.distance_band,
        }
        for placeholder, value in replacements.items():
            message = message.replace(placeholder, value)
        return message.strip()

    def _record_distant_cue_state_changed(
        self,
        *,
        cue: Any,
        old_active: bool,
        new_active: bool,
        initialized_before: bool,
        visible_recipient_count: int,
        delivery_skipped_reason: Optional[str],
    ) -> None:
        recorder = self._trace_recorder
        if recorder is None:
            return
        try:
            from ai_rpg_world.application.trace import TraceEventKind

            source = getattr(cue, "source", None)
            recorder.record(
                TraceEventKind.DISTANT_CUE_STATE_CHANGED,
                tick=self.current_tick(),
                cue_id=str(getattr(cue, "cue_id", "")),
                old_active=old_active,
                new_active=new_active,
                initialized_before=initialized_before,
                origin_area_id=str(getattr(cue, "origin_area_id", "")),
                source_kind=str(getattr(source, "kind", "")),
                source_state_key=str(getattr(source, "state_key", "")),
                visible_recipient_count=visible_recipient_count,
                delivery_skipped_reason=delivery_skipped_reason,
            )
        except Exception:
            logger.warning(
                "DISTANT_CUE_STATE_CHANGED trace record failed: cue_id=%s",
                getattr(cue, "cue_id", "<unknown>"),
                exc_info=True,
            )

    def _record_distant_cue_skipped(self, *, cue: Any, reason: str) -> None:
        """debug profile のときだけ cue 境界検出の skipped 理由を trace に残す。"""
        if not bool(getattr(self._state_builder, "_distant_view_trace_enabled", False)):
            return
        recorder = self._trace_recorder
        if recorder is None:
            return
        try:
            from ai_rpg_world.application.trace import TraceEventKind

            recorder.record(
                TraceEventKind.DISTANT_VIEW_SKIPPED,
                tick=self.current_tick(),
                cue_id=str(getattr(cue, "cue_id", "")),
                origin_area_id=str(getattr(cue, "origin_area_id", "")),
                skipped_reasons=[reason],
                source_kind=str(getattr(getattr(cue, "source", None), "kind", "")),
                source_state_key=str(
                    getattr(getattr(cue, "source", None), "state_key", "")
                ),
            )
        except Exception:
            logger.warning(
                "DISTANT_VIEW_SKIPPED trace record failed: cue_id=%s reason=%s",
                getattr(cue, "cue_id", "<unknown>"),
                reason,
                exc_info=True,
            )

    def _record_distant_cue_delivered(
        self,
        *,
        cue: Any,
        player_id: PlayerId,
        spot_id: SpotId,
        visible: DistantViewVisibleCandidate,
        schedules_turn: bool,
    ) -> None:
        recorder = self._trace_recorder
        if recorder is None:
            return
        try:
            from ai_rpg_world.application.trace import TraceEventKind

            recorder.record(
                TraceEventKind.DISTANT_CUE_DELIVERED,
                tick=self.current_tick(),
                player_id=int(player_id),
                cue_id=str(getattr(cue, "cue_id", "")),
                spot_id=spot_id.value,
                direction=visible.direction,
                distance_band=visible.distance_band,
                schedules_turn=schedules_turn,
            )
        except Exception:
            logger.warning(
                "DISTANT_CUE_DELIVERED trace record failed: cue_id=%s player_id=%s",
                getattr(cue, "cue_id", "<unknown>"),
                int(player_id),
                exc_info=True,
            )

    def _time_label(self) -> str:
        """ゲーム内時刻ラベルを生成する。

        Phase: 時刻の二重系統を解消するため day_night サイクルから計算する。
        旧実装は `tick * 5 分` で固定 24h cycle だったが、シナリオの
        ticks_per_day と整合せず「現在時刻: 1:00 / 時刻帯: 朝」のような
        矛盾表示を生んでいた。

        新実装:
        - day_night_stage が宣言されていれば、その ticks_per_day を 24h
          として換算する (1 tick = 24h / ticks_per_day)。
        - 宣言が無いシナリオ (脱出ゲーム等) は旧フォールバック (5 分/tick)
          を維持して後方互換。
        """
        tick = self.current_tick()
        # day_night があれば ticks_per_day ベースで 24h 換算
        if self._day_night_stage is not None:
            cycle = self._day_night_stage._cycle
            ticks_per_day = cycle.ticks_per_day
            day_index = tick // ticks_per_day
            tick_in_day = tick % ticks_per_day
            # 1 日 24 時間を ticks_per_day で分割
            minutes_per_tick = (24 * 60) // ticks_per_day
            total_minutes = tick_in_day * minutes_per_tick
            h, m = divmod(total_minutes, 60)
            prefix = "深夜 " if h < 6 else ""
            return f"Day {day_index + 1} {prefix}{h}:{m:02d}"
        # フォールバック: 旧挙動 (5 分/tick の 24h cycle)
        hours = (tick * 5) % (24 * 60)
        h, m = divmod(hours, 60)
        return f"深夜 {h}:{m:02d}" if h < 6 else f"{h}:{m:02d}"

    def _append_food_spoiled_observation(
        self,
        item_instance_id: Any,
        item_spec_id: Any,
        spec_name: str,
    ) -> None:
        """Phase D-3a: 食料が腐ったタイミングで全プレイヤーに観測を流す。

        ⚠ 直接呼び出しは旧 per-instance 経路 (trace の詳細用に残してある)。
        観測は `_append_food_spoiled_batch_observation` 経由の集約版を使う。
        この per-instance 経路は test や外部からの直接呼び出しで使う想定。

        weather と同じく world event 扱い (誰の所持品でも気付ける匂い等を
        想定)。spec_name が空文字列なら spec 名解決に失敗しているので
        sentinel 表示にフォールバック。
        """
        display_name = spec_name or f"アイテム#{item_instance_id.value}"
        message = f"{display_name}が腐った。"
        output = ObservationOutput(
            prose=message,
            structured={
                "type": "food_spoiled",
                "item_spec_id": item_spec_id.value,
                "item_instance_id": item_instance_id.value,
                "spec_name": spec_name,
            },
            observation_category="environment",
            schedules_turn=False,
            breaks_movement=False,
        )
        for player_id in self.get_player_ids():
            self._emit_observation_directly(player_id, output)

    def _append_food_spoiled_batch_observation(
        self,
        spoiled: Any,
    ) -> None:
        """第24回実験 (#343) + #356 後続: 食料腐敗 観測を **日単位で集約**。

        旧 (#350 同 tick 集約):
            「野いちごが3つ腐った。」 (同 tick 内のみ aggregate)
            → 1 日に渡って 8 個が別 tick で腐ると 8 件の観測が走る

        新 (本 PR): 日 (24 tick) を跨いで pending buffer に貯め、日境界
        または game-end の直前に **1 日分まとめて** flush する:
            「今日は野いちごが5個、椰子の実が2個腐った。」

        spoiled は Sequence[(ItemInstanceId, ItemSpecId, str)]。
        """
        if not spoiled:
            return
        # 当日分の buffer に積む。flush は day boundary で行う (下記参照)。
        # field 化済 (#375 後続レビュー対応): 遅延 hasattr 初期化を廃止。
        # 当日 day index を計算 (cycle が無いシナリオは tick そのまま使う)
        ticks_per_day = self._ticks_per_day_or_default()
        current_day = self.current_tick() // max(1, ticks_per_day)
        # 日が変わっていたら前日分を flush してから新日のバッファに積む
        if (
            self._pending_spoiled_day is not None
            and self._pending_spoiled_day != current_day
        ):
            self._flush_pending_food_spoiled()
        self._pending_spoiled_day = current_day
        for instance_id, spec_id, spec_name in spoiled:
            sid = int(spec_id.value)
            entry = self._pending_spoiled.setdefault(
                sid,
                {
                    "spec_id": sid,
                    "spec_name": spec_name,
                    "instance_ids": [],
                },
            )
            entry["instance_ids"].append(int(instance_id.value))

    def _ticks_per_day_or_default(self) -> int:
        """day_night_config があればそこから ticks_per_day を取り、無ければ 24。"""
        cfg = getattr(self.scenario, "day_night_config", None)
        if cfg is None:
            return 24
        try:
            cycle = cfg.cycle
            if cycle is None:
                return 24
            return int(cycle.ticks_per_day)
        except AttributeError:
            return 24

    def _flush_pending_food_spoiled(self) -> None:
        """day boundary 等で pending 腐敗バッファを 1 件の集約観測として配信する。

        flush 後は buffer を空に戻し、`_pending_spoiled_day` も None にする。
        spec 数が複数なら「今日は野いちごが5個、椰子の実が2個腐った。」と
        まとめる。spec 1 種なら「今日は野いちごが5個腐った。」とシンプルに。
        """
        pending = getattr(self, "_pending_spoiled", None) or {}
        if not pending:
            self._pending_spoiled = {}
            self._pending_spoiled_day = None
            return
        # 「{spec_name}が{n}個」形のフラグメントを spec 順で並べる
        fragments: list[str] = []
        all_instance_ids: list[int] = []
        for entry in pending.values():
            count = len(entry["instance_ids"])
            display_name = entry["spec_name"] or f"アイテム#{entry['spec_id']}"
            unit = "個"
            fragments.append(f"{display_name}が{count}{unit}")
            all_instance_ids.extend(entry["instance_ids"])
        if len(fragments) == 1:
            message = f"今日は{fragments[0]}腐った。"
        else:
            message = "今日は" + "、".join(fragments) + "腐った。"
        output = ObservationOutput(
            prose=message,
            structured={
                "type": "food_spoiled",
                "aggregation": "daily",
                "day": self._pending_spoiled_day,
                "spec_summary": [
                    {
                        "item_spec_id": e["spec_id"],
                        "spec_name": e["spec_name"],
                        "count": len(e["instance_ids"]),
                    }
                    for e in pending.values()
                ],
                "item_instance_ids": all_instance_ids,
            },
            observation_category="environment",
            schedules_turn=False,
            breaks_movement=False,
        )
        for player_id in self.get_player_ids():
            self._emit_observation_directly(player_id, output)
        self._pending_spoiled = {}
        self._pending_spoiled_day = None

    def _append_weather_observation(self, weather_state: Any) -> None:
        # Issue #276 経路二重化解消: ``_emit_observation_directly`` 経由に統一。
        message = f"外の天候が変わった: {weather_state.weather_type.value}（強度 {weather_state.intensity:.1f}）"
        output = ObservationOutput(
            prose=message,
            structured={
                "type": "weather_changed",
                "weather_type": weather_state.weather_type.value,
                "intensity": weather_state.intensity,
            },
            observation_category="environment",
            schedules_turn=True,
            breaks_movement=False,
        )
        for player_id in self.get_player_ids():
            self._emit_observation_directly(player_id, output)

    # ── ゲーム終了判定 ──

    def check_game_end(self) -> GameEndResult:
        # END_ON_ALL_DOWN はシナリオ内の勝敗規則ではなく、実験を行動不能状態で
        # 回し続けないための外的停止。個人結果規則や end 条件の有無に関係なく、
        # 宣言された世界の判定より先に一つの入口で評価する。
        registry = self._player_outcome_registry
        if (
            self._should_end_on_all_down()
            and registry is not None
            and self._all_players_unable_to_act(registry)
        ):
            return GameEndResult(
                is_ended=True,
                result=None,
                reason=(
                    "外的停止 END_ON_ALL_DOWN: 行動可能プレイヤーがいない "
                    "(全員 down または outcome 確定済み)"
                ),
                player_outcomes=registry.snapshot(),
            )
        return self._check_game_end_collective_mode()

    def _should_end_on_all_down(self) -> bool:
        """END_ON_ALL_DOWN による外的停止が有効かを返す。"""
        cfg = getattr(self, "_runtime_config", None)
        return bool(getattr(cfg, "end_on_all_down", False))

    def _all_players_unable_to_act(self, registry: Any) -> bool:
        """全 player が outcome 確定済み、または unresolved でも down 済みかを返す。"""
        player_ids = self.get_player_ids()
        if not player_ids:
            return False
        for player_id in player_ids:
            outcome = registry.get_outcome(player_id)
            if outcome.is_resolved:
                continue
            status = self._player_status_repo.find_by_id(player_id)
            if status is None or getattr(status, "is_down", False) is not True:
                return False
        return True

    def _check_game_end_collective_mode(self) -> GameEndResult:
        """v1 / 既存シナリオ用の集団 win/lose 判定。挙動は従来通り。"""
        graph = self._spot_graph_repo.find_graph()
        flags = self._world_flag_state.as_frozen_set()
        player_ids = self.get_player_ids()
        from ai_rpg_world.domain.common.value_object import WorldTick
        tick = WorldTick(self._tick)
        # 陣営条件 (SURVIVING_PLAYERS_WITH_STATE_AT_MOST) の判定材料。
        # 役割は PlayerStatusAggregate.state、生死は outcome registry が持つ。
        # 渡さないと評価器が例外を投げる (黙って未成立にしない)。
        #
        # 毎 tick 全員分を引くので、陣営条件を使わないシナリオでは集めない。
        from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import (
            GameEndConditionTypeEnum,
        )
        all_end_conditions = (
            *self.scenario.win_conditions,
            *self.scenario.lose_conditions,
            *self.scenario.end_conditions,
        )
        needs_faction_inputs = any(
            c.condition_type in (
                GameEndConditionTypeEnum.SURVIVING_PLAYERS_WITH_STATE_AT_MOST,
                GameEndConditionTypeEnum.SURVIVING_PLAYERS_WITH_STATE_AT_MOST_OTHER_STATE,
            )
            for c in all_end_conditions
        )
        needs_outcome_inputs = needs_faction_inputs or any(
            c.condition_type
            is GameEndConditionTypeEnum.ALL_PLAYER_OUTCOMES_RESOLVED
            for c in all_end_conditions
        )
        player_states = (
            self._collect_player_states(player_ids) if needs_faction_inputs else None
        )
        player_outcomes = (
            self._collect_player_outcomes(player_ids) if needs_outcome_inputs else None
        )
        for wc in self.scenario.win_conditions:
            result = self._game_end_evaluator.evaluate(
                graph, wc, flags, player_ids, tick,
                player_states=player_states, player_outcomes=player_outcomes,
                result_on_match=GameResultEnum.WIN,
            )
            if result.is_ended:
                return result
        for lc in self.scenario.lose_conditions:
            result = self._game_end_evaluator.evaluate(
                graph, lc, flags, player_ids, tick,
                player_states=player_states, player_outcomes=player_outcomes,
                result_on_match=GameResultEnum.LOSE,
            )
            if result.is_ended:
                return result
        for ec in self.scenario.end_conditions:
            result = self._game_end_evaluator.evaluate(
                graph, ec, flags, player_ids, tick,
                player_states=player_states, player_outcomes=player_outcomes,
                result_on_match=None,
            )
            if result.is_ended:
                return result
        return GameEndResult(is_ended=False, result=None, reason="ゲーム続行中")

    def _collect_player_states(self, player_ids) -> Dict[int, Dict[str, Any]]:
        """陣営条件が役割を読むための state 表を作る。"""
        states: Dict[int, Dict[str, Any]] = {}
        for pid in player_ids:
            status = self._player_status_repo.find_by_id(pid)
            states[int(pid)] = dict(status.state) if status is not None else {}
        return states

    def _collect_player_outcomes(self, player_ids) -> Dict[int, Any]:
        """陣営条件が生死を読むための outcome 表を作る。

        registry が未配線のシナリオでは全員 UNRESOLVED として扱う。陣営条件を
        書いていないシナリオではこの表自体が参照されないので影響しない。
        """
        from ai_rpg_world.domain.player.enum.player_outcome_enum import (
            PlayerOutcomeEnum,
        )
        registry = self._player_outcome_registry
        if registry is None:
            return {int(pid): PlayerOutcomeEnum.UNRESOLVED for pid in player_ids}
        return {int(pid): registry.get_outcome(pid) for pid in player_ids}

    def get_player_spot_name(self, player_id: PlayerId) -> str:
        graph = self._spot_graph_repo.find_graph()
        if self._player_perception_policy.is_departed(player_id):
            spot_id = self._departed_position_store.find(player_id)
            if spot_id is None:
                raise RuntimeError(f"去った主体の位置がありません: {player_id}")
        else:
            spot_id = graph.get_entity_spot(EntityId.create(int(player_id)))
        return graph.get_spot(spot_id).name

    def get_player_spot_id(self, player_id: PlayerId) -> Optional[str]:
        """プレイヤーが現在いる spot の生 ID 文字列を返す (見つからなければ None)。

        trace の ``position_change`` event payload に乗せる用途。
        例: スポット間移動の trail 描画。
        """
        try:
            graph = self._spot_graph_repo.find_graph()
            if self._player_perception_policy.is_departed(player_id):
                spot_id = self._departed_position_store.find(player_id)
            else:
                spot_id = graph.get_entity_spot(EntityId.create(int(player_id)))
        except Exception:
            return None
        if spot_id is None:
            return None
        # SpotId は value_object なので value を取り出す
        value = getattr(spot_id, "value", None)
        if value is None:
            return str(spot_id)
        return str(value)


_LLM_TOOL_MODE_DEFAULT = "default"
_LLM_TOOL_MODE_PURE_SPOT_GRAPH = "pure_spot_graph"


def _build_context_format_strategy_from_config(
    cfg: "ResolvedLlmRuntimeConfig",
) -> SectionBasedContextFormatStrategy:
    """resolved config から context format strategy を組む。"""
    return SectionBasedContextFormatStrategy(section_order=cfg.prompt_section_order)


def _build_short_term_memory(
    cfg: "ResolvedLlmRuntimeConfig",
    *,
    scenario: Any,
    world_character: Optional[CharacterPromptInput],
    persona_block: str,
    event_store: UnifiedRecentEventStore,
) -> IShortTermMemory:
    """PR #451 (PR 6/6): 短期記憶を **「全部揃ってから 1 回 build」** で作る。

    旧構造 (PR #439-#449):
      1. ``_build_short_term_memory_from_config(cfg)`` で setter 用の「殻」だけ作る
         (summary_service=None / template fallback only)
      2. runtime / llm_client が完成した後に
         ``_wire_short_term_llm_services()`` が setter で LLM 経路を後注入

      → setter 呼び忘れで silent failure を量産 (PR #444 で実害発生)。

    新構造 (本 PR):
      1. cfg + scenario + persona から LLM client / summary services /
         persona resolver を **構築時点で全部揃える**
      2. ``SummarizingShortTermMemory(summary_service=X, long_summary_service=Y,
         persona_resolver=Z)`` を ctor 一発で組む
      3. ``set_summary_services`` 経由の後注入経路は廃止

    trace_recorder / current_tick は runtime instance に依存するため、別経路
    (``WorldRuntime.set_trace_recorder``) で provider を差し替える。これは
    PR #449 の NullObject 正規化により呼び忘れても本体が止まらない。

    Args:
        cfg: resolved runtime config (env を 1 度だけ読んだ DTO)
        scenario: ScenarioLoader の結果 (persona resolver 構築に使う)
        world_character: 操作対象キャラ (rich persona を割り当てる対象)
        persona_block: world_character 由来の persona テキスト
    """
    from ai_rpg_world.application.llm.wiring.feature_flags import (
        SHORT_TERM_MEMORY_KIND_ROLLING_SUMMARY,
        log_short_term_memory_kind_state,
    )

    log_short_term_memory_kind_state(cfg.short_term_memory_kind)
    if cfg.short_term_memory_kind != SHORT_TERM_MEMORY_KIND_ROLLING_SUMMARY:
        return DefaultSlidingWindowMemory(
            event_store=event_store,
            turn_cap=cfg.short_term_memory_turn_cap,
            compact_turn_count=cfg.short_term_memory_turn_compact_count,
        )

    # rolling_summary 経路: LLM 経路を **構築時点で揃える**
    from ai_rpg_world.application.llm.services.summarizing_short_term_memory import (
        SummarizingShortTermMemory,
    )
    from ai_rpg_world.application.llm.services.short_term_memory_long_summary_service import (
        ShortTermMemoryLongSummaryService,
    )
    from ai_rpg_world.application.llm.services.short_term_memory_summary_service import (
        ShortTermMemorySummaryService,
    )
    from ai_rpg_world.application.llm.wiring._llm_client_factory import (
        create_llm_client_from_config,
    )
    from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient

    summary_service = None
    long_summary_service = None
    persona_resolver = None
    if cfg.llm_client_kind == "litellm":
        try:
            client = create_llm_client_from_config(cfg)
        except Exception:
            logger.exception("LLM client factory failed; short-term LLM services disabled")
            client = None
        if isinstance(client, LiteLLMClient):
            summary_service = ShortTermMemorySummaryService(client)
            long_summary_service = ShortTermMemoryLongSummaryService(client)
            persona_resolver = _build_persona_resolver(
                scenario=scenario,
                world_character=world_character,
                persona_block=persona_block,
            )
            logger.info(
                "short-term memory: LLM 経路を ctor 注入 (rolling_summary + LiteLLM)。"
                "L4 / L5 は LLM 圧縮で生成される。"
            )
        else:
            logger.info(
                "LLM_CLIENT=litellm が未取得。short-term memory は template fallback "
                "only で動作 (L4 / L5 の LLM 圧縮は無効)。"
            )

    return SummarizingShortTermMemory(
        summary_service=summary_service,
        long_summary_service=long_summary_service,
        persona_resolver=persona_resolver,
        event_store=event_store,
        turn_cap=cfg.short_term_memory_turn_cap,
        compact_turn_count=cfg.short_term_memory_turn_compact_count,
    )


def _build_persona_resolver(
    *,
    scenario: Any,
    world_character: Optional[CharacterPromptInput],
    persona_block: str,
) -> Callable[[int], tuple[str, str]]:
    """player_id -> (name, persona_block) を引ける callable を組む。

    旧 _wire_short_term_llm_services 内に inline されていたロジックを抽出。
    subjective scheduler wiring と同じ規則:
        - world_character 指定 player には rich persona
        - それ以外は fallback persona
    """
    name_persona_by_pid: dict[int, tuple[str, str]] = {}
    if scenario.player_spawns:
        if len(scenario.player_spawns) > 1 and world_character is not None:
            ec_cid = (world_character.character_id or "").strip()
            ec_name = (world_character.name or "").strip()
            for s in scenario.player_spawns:
                if (ec_cid and s.string_id == ec_cid) or (ec_name and s.name == ec_name):
                    name_persona_by_pid[int(s.player_id)] = (s.name, persona_block)
                else:
                    fallback = build_persona_block_from_character(
                        None, fallback_display_name=s.name
                    )
                    name_persona_by_pid[int(s.player_id)] = (s.name, fallback)
        else:
            for s in scenario.player_spawns:
                name_persona_by_pid[int(s.player_id)] = (s.name, persona_block)

    def _resolver(pid: int) -> tuple[str, str]:
        return name_persona_by_pid.get(int(pid), (f"player_{pid}", ""))

    return _resolver


def create_world_runtime(
    scenario_path: Path,
    *,
    world_character: Optional[CharacterPromptInput] = None,
    llm_turn_trigger: Optional[ILlmTurnTrigger] = None,
    include_todo_tools: Optional[bool] = None,
    config: Optional["ResolvedLlmRuntimeConfig"] = None,
) -> WorldRuntime:
    """シナリオ JSON からゲームランタイムを構築する。

    Args:
        llm_turn_trigger: 省略時は :class:`WorldStandaloneNoopLlmTurnTrigger`。
            スポットグラフのティック後フック用。プレゼン層のセッションでは
            ``runtime.set_simulation_llm_turn_trigger(…)`` で本物に差し替え可能。
        include_todo_tools: ``True`` で TODO 系を含める従来構成、``False`` で
            純スポットグラフモード (TODO 系を除外、speech は残す)。``None``
            (既定) の場合は環境変数 ``LLM_TOOL_MODE`` から解決する。Issue #155
            (TODO 設計の再評価) の判断材料を取るための比較実験用。
        config: PR #448 (PR 3/6): LLM runtime 設定の単一窓口。省略時は
            ``ResolvedLlmRuntimeConfig.from_mapping()`` で空設定から既定値を
            resolve。entrypoint (run_scenario_experiment 等) で既に
            from_mapping() 済みの cfg を渡せば、**run_start trace と
            実 wiring の同一性を構造で保証する**ための引数。
    """
    # 引数 cfg が来ていればそれを使う。来ていなければ空設定の既定値で構築する。
    # 実験に意味を持つ設定は環境変数から読まない。
    from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
        ResolvedLlmRuntimeConfig,
    )

    if config is None:
        config = ResolvedLlmRuntimeConfig.from_mapping()

    loader = ScenarioLoader()
    scenario = loader.load_from_file(scenario_path)

    fallback_name = (
        scenario.player_spawns[0].name if scenario.player_spawns else "探索者"
    )
    persona_block = build_persona_block_from_character(
        world_character,
        fallback_display_name=fallback_name,
    )
    # 層2 (#526 / U5): 勝敗条件を宣言するシナリオか (= goal あり) を導出する。
    # win/lose/outcome のいずれかがあれば goal 前提の文面、無ければ永続世界として
    # escape/goal 前提 (脱出できない / 勝利条件・最終目的) を中立化する。既存シナリオは
    # 全て game_end_conditions を持つので has_goal=True となり prompt は不変。
    # 目的層の goal seed (locked 判定) とロジックを共有する (_scenario_has_goal)。
    _has_goal = _scenario_has_goal(scenario)
    safe_intro = safe_world_intro_text(scenario.metadata, has_goal=_has_goal)
    # 見取り図・陣営の内訳・点検の割り当ては **シナリオのデータから組み立てる**。
    #
    # 以前は llm_public_intro に手で写されていて、#938 で人数とタスクを
    # 変えたときに 4 箇所ずれた。実 run 009 のエージェントは存在しない世界の
    # 前提で推論していた。写しは必ず腐る。
    #
    # どれも run 中変わらないので、システムプロンプトに置けばプレフィックス
    # キャッシュに載る。会議中も見えるので「会議のときは地図を出す」という
    # フェーズ分岐を書かずに済む。
    metadata = scenario.metadata
    briefing = build_world_briefing(
        spots=list(scenario.graph.iter_spot_nodes()),
        connections=list(scenario.graph.all_connections()),
        players=scenario.player_spawns,
        show_world_map=metadata.show_world_map,
        minutes_per_tick=_minutes_per_tick(scenario),
        interiors=scenario.interiors,
        role_labels=metadata.role_labels,
        required_task_count=_required_task_count(scenario),
        task_winner_role="crew",
        meeting_enabled=scenario.meeting_enabled,
        meeting_tick_limit=scenario.meeting_tick_limit,
        meeting_silence_limit_ticks=scenario.meeting_silence_limit_ticks,
        meeting_cooldown_ticks=scenario.meeting_cooldown_ticks,
    )
    if briefing:
        safe_intro = f"{safe_intro}\n\n{briefing}" if safe_intro else briefing
    participants = _other_explorer_names_for_world_system_prompt(
        scenario.player_spawns, world_character
    )
    system_prompt_text = build_world_system_prompt(
        world_title=scenario.metadata.title,
        persona_block=persona_block,
        safe_intro=safe_intro,
        participant_names=participants,
        enable_string_seed_of_thought=config.escape_llm_ssot_enabled,
        expected_result_policy=config.expected_result_policy,
        has_goal=_has_goal,
    )

    # Issue #264 第16回実験 fix: シナリオに player_spawns がある場合、
    # 各 player に persona を埋めた system prompt を個別に構築する。
    # これにより player 2 (例: リン) は「自分はリン」という persona block を
    # 受け取り、自呼び回帰 (リンが「リン、」と speech する) が解消される。
    #
    # Issue #526 後続: 旧コードは ``len(player_spawns) > 1`` のときだけ
    # per-player path を走らせていた。これは「1 player なら world_character の
    # legacy single-player path が persona を作るから不要」という前提だったが、
    # ``world_character is None`` で 1 player を実験する recall_probe 系で
    # ``spawn.persona_prompt`` が完全に無視される設計バグになっていた。
    # 制約を外して **player_spawns があれば常に per-player persona を構築** する。
    #
    # ロジック:
    #   - spawn.persona_prompt が設定されていれば最優先
    #   - world_character がこの spawn を指していれば rich persona
    #   - それ以外は fallback persona (= スポーン名から生成された最小ペルソナ)
    #   - participant_names は各 player から見た「自分以外の探索者」のリスト
    system_prompts_by_player_id: Dict[int, str] = {}
    if scenario.player_spawns:
        # world_character に一致する spawn を特定
        world_spawn: Optional[PlayerSpawnConfig] = None
        if world_character is not None:
            ec_cid = (world_character.character_id or "").strip()
            ec_name = (world_character.name or "").strip()
            for s in scenario.player_spawns:
                if (ec_cid and s.string_id == ec_cid) or (ec_name and s.name == ec_name):
                    world_spawn = s
                    break

        for spawn in scenario.player_spawns:
            # この spawn から見た「他者」名リスト。仲間の印はここで世界内の
            # 表示へ解決し、role の生値を汎用 prompt builder へ渡さない。
            viewer_role = str(spawn.initial_state.get("role") or "")
            reveals_allies = viewer_role in scenario.mutually_known_roles
            other_names = tuple(
                (
                    f"{other.name} (あなたと同じ側)"
                    if reveals_allies
                    and other.initial_state.get("role") == viewer_role
                    else other.name
                )
                for other in scenario.player_spawns
                if other is not spawn
            )
            # この spawn のペルソナ (優先度):
            #   1. spawn.persona_prompt (Phase E): シナリオ JSON で個別宣言された
            #      ペルソナ。多 player シナリオの第一選択肢
            #   2. world_character がこの spawn を指している → rich persona
            #      (脱出ゲーム単 player モード用の旧経路)
            #   3. fallback (スポーン名ベース generic persona)
            if spawn.persona_prompt is not None:
                this_persona = spawn.persona_prompt
            elif world_character is not None and spawn is world_spawn:
                this_persona = persona_block  # rich (既に上で構築済み)
            else:
                this_persona = build_persona_block_from_character(
                    None,  # fallback path
                    fallback_display_name=spawn.name,
                )
            # 個人の人物像を先、役職に共通する不変知識を後ろへ固定して連結する。
            # tick や現在の所持品で順序・有無を変えず、system prompt の接頭辞を守る。
            role_persona = scenario.role_personas.get(viewer_role)
            if role_persona:
                this_persona = f"{this_persona}\n\n{role_persona}"
            system_prompts_by_player_id[int(spawn.player_id)] = (
                build_world_system_prompt(
                    world_title=scenario.metadata.title,
                    persona_block=this_persona,
                    safe_intro=safe_intro,
                    participant_names=other_names,
                    enable_string_seed_of_thought=config.escape_llm_ssot_enabled,
                    expected_result_policy=config.expected_result_policy,
                    has_goal=_has_goal,
                )
            )

    data_store = InMemoryDataStore()

    spot_graph_repo = InMemorySpotGraphRepository(scenario.graph)

    spot_interior_repo = InMemorySpotInteriorRepository(data_store=data_store)
    for spot_id, interior in scenario.interiors.items():
        spot_interior_repo.save(spot_id, interior)

    item_repo = InMemoryItemRepository(data_store)
    item_spec_repo = InMemoryItemSpecRepository()

    for item_def in scenario.item_spec_definitions:
        # Phase F: consume_effect が non-None なら CONSUMABLE として登録する。
        # consume_effect が無いアイテムは従来通り QUEST (素材・装備・道具)。
        # ItemSpec.__post_init__ の invariant: consume_effect は CONSUMABLE 時
        # のみ非 None で居られる。
        item_type = (
            ItemType.CONSUMABLE if item_def.consume_effect is not None
            else ItemType.QUEST
        )
        spec = ItemSpecReadModel(
            item_spec_id=item_def.spec_id,
            name=item_def.name,
            item_type=item_type,
            rarity=Rarity.COMMON,
            description=item_def.description,
            max_stack_size=MaxStackSize(1),
            is_light_source=item_def.is_light_source,
            # Phase D-2: 食料腐敗。loader が JSON から取得した値をそのまま渡す。
            # None なら腐らないアイテム (道具・装備・水)。
            spoils_after_ticks=item_def.spoils_after_ticks,
            # Phase F: 消費効果。None なら use_item が reject する。
            consume_effect=item_def.consume_effect,
            # PR β: 疲労回復量。loader 経由で JSON から。0 なら効果なし。
            fatigue_recovery=item_def.fatigue_recovery,
            # Issue #794 D: item spec 作者文の一般用途ヒント。
            usage_hint=item_def.usage_hint or None,
            # item_type とは別軸の作者分類。prompt 表示の既定文言にだけ使う。
            category=item_def.category,
        )
        item_spec_repo.save(spec)

    player_status_repo = InMemoryPlayerStatusRepository(data_store)
    player_inventory_repo = InMemoryPlayerInventoryRepository(data_store)
    from ai_rpg_world.domain.player.service.player_outcome_registry import (
        PlayerOutcomeRegistry,
    )

    outcome_registry = PlayerOutcomeRegistry.new_for_players(
        [PlayerId(spawn.player_id) for spawn in scenario.player_spawns]
    )
    player_life_query = PlayerLifeQuery(
        player_status_repository=player_status_repo,
        player_outcome_registry=outcome_registry,
        departed_agents_enabled=scenario.departed_agents_enabled,
    )
    from ai_rpg_world.application.player.services.player_perception_policy import (
        PlayerPerceptionPolicy,
    )

    player_perception_policy = PlayerPerceptionPolicy(
        outcome_registry=outcome_registry,
        departed_agents_enabled=scenario.departed_agents_enabled,
    )

    # PR4 (Encounter Memory): spawn loop で初期 spot encounter を直接記録する
    # ため、ここで先に instance を生成する。line 2132 で ``graph.clear_events()``
    # が走るので、spawn 時の EntityEnteredSpotEvent (from_spot_id=None) は
    # publisher 経由では届かない。直接 observe する形で「世界に登場した最初の
    # 場所」を familiarity に残す。
    encounter_memory = InMemoryEncounterMemory()

    graph = spot_graph_repo.find_graph()
    for spawn in scenario.player_spawns:
        pid = PlayerId(spawn.player_id)
        exp_table = ExpTable(base_exp=100.0, exponent=1.5)
        # PR 2 (#227): PlayerSpeechApplicationService が status.current_coordinate
        # を要求 (タイル系の SpeechRecipientStrategy 用) するため、spot_graph
        # でも sentinel として Coordinate(0,0,0) を埋める。
        # SpotGraphSpeechRecipientStrategy は coordinate を読まないので値は
        # 影響しない。
        status = PlayerStatusAggregate(
            player_id=pid,
            base_stats=BaseStats(max_hp=100, max_mp=50, attack=10, defense=10, speed=10, critical_rate=0.05, evasion_rate=0.05),
            stat_growth_factor=StatGrowthFactor(hp_factor=1.0, mp_factor=1.0, attack_factor=1.0, defense_factor=1.0, speed_factor=1.0, critical_rate_factor=0.0, evasion_rate_factor=0.0),
            exp_table=exp_table,
            growth=Growth(level=1, total_exp=0, exp_table=exp_table),
            # シナリオが宣言した所持金の初期値。宣言しなければ 0 で、
            # 経済を持たない既存シナリオの挙動は変わらない。
            gold=Gold(spawn.initial_gold),
            hp=Hp(value=100, max_hp=100),
            mp=Mp(value=50, max_mp=50),
            stamina=Stamina(value=100, max_stamina=100),
            navigation_state=PlayerNavigationState.from_parts(
                current_spot_id=spawn.spawn_spot_id,
                current_coordinate=Coordinate(0, 0, 0),
            ),
            spot_navigation_state=PlayerSpotNavigationState.at_rest(spawn.spawn_spot_id),
            # シナリオが宣言した初期 state (役割・印など) をそのまま載せる。
            #
            # ここも長らく抜けていた。loader は players[].initial_state を
            # 検証までして player_spawns に載せていたのに、**本番経路から
            # 一度も読まれていなかった** (initial_items と同じ形の穴)。
            # 適用されないと PLAYER_STATE_IS / TARGET_PLAYER_STATE_IS を
            # 使う宣言はシナリオからは永久に成立せず、しかも失敗文は作者が
            # 書いた文言が返るので原因が文言の裏に隠れる。
            state=dict(spawn.initial_state) if spawn.initial_state else None,
        )
        player_status_repo.save(status)
        player_inventory_repo.save(PlayerInventoryAggregate(player_id=pid))
        # シナリオが宣言した初期所持品を実際に渡す。
        #
        # ここが長らく抜けていた。loader は initial_items を parse して
        # player_spawns に載せ、grant_initial_items_to_inventory も存在した
        # のに、**本番経路から一度も呼ばれていなかった**。宣言は読まれるだけ
        # で誰にも配られず、実 run では全員が手ぶらで始まっていた。
        # 各テストが自分で helper を呼んでフィクスチャを作っていたため、
        # テストからも見えなかった。
        #
        # snapshot からの再開でも二重にならない。PlayerInventorySubsystemCodec
        # の restore は restore_from_data + save で inventory 集約を丸ごと
        # 置き換えるので、ここで配ったぶんは復元時に上書きされる
        # (tests/demos/test_initial_items_are_granted_at_startup.py が固定)。
        if spawn.initial_items:
            grant_initial_items_to_inventory(
                pid,
                spawn.initial_items,
                item_repo,
                item_spec_repo,
                player_inventory_repo,
                overflow_sink=refuse_overflow("起動時の初期所持品"),
            )

        eid = EntityId.create(spawn.player_id)
        if not graph.presence_at(spawn.spawn_spot_id).is_present(eid):
            graph.place_entity(eid, spawn.spawn_spot_id)
        # PR4: 初回 spawn の spot encounter を直接記録する (handler 経由では
        # 拾えない、上のコメント参照)。tick は 0 (= scenario 開始時点)。
        spawn_spot_str_id = scenario.id_mapper.get_str(
            "spot", spawn.spawn_spot_id.value
        )
        encounter_memory.observe(
            pid, EncounterKey.spot(spawn_spot_str_id), 0
        )

    # ── Phase B-2a: モンスターの初期配置 ──
    # シナリオで宣言された MonsterTemplate を template repo に登録し、
    # initial_placements を MonsterAggregate.reconstitute で実体化して
    # monster_repo + graph (place_monster) に登録する。動的 spawn (時間帯
    # 条件) は Phase B-2b の SpotGraphMonsterSpawnService が担う。
    monster_repo = InMemoryMonsterAggregateRepository(data_store)
    monster_template_repo = InMemoryMonsterTemplateRepository()
    skill_loadout_repo = InMemorySkillLoadoutRepository(data_store)
    if scenario.monster_templates or scenario.monster_placements:
        # NOTE: Coordinate / WorldTick はモジュールトップで import 済 (player
        # setup でも使われている)。ここでローカル import すると Python の
        # 関数スコープ規則で「local variable referenced before assignment」
        # になり、上の player 初期化を壊す。
        from ai_rpg_world.domain.monster.aggregate.monster_aggregate import (
            MonsterAggregate,
        )
        from ai_rpg_world.domain.monster.value_object.monster_id import MonsterId
        from ai_rpg_world.domain.skill.aggregate.skill_loadout_aggregate import (
            SkillLoadoutAggregate,
        )
        from ai_rpg_world.domain.skill.value_object.skill_loadout_id import (
            SkillLoadoutId,
        )
        from ai_rpg_world.domain.world.value_object.world_object_id import (
            WorldObjectId,
        )
        from ai_rpg_world.domain.common.value_object import WorldTick

        for st in scenario.monster_templates:
            monster_template_repo.save(st.template)

        # MonsterId / WorldObjectId / SkillLoadoutId の単純な incrementing
        # 採番。本サービスはシナリオ起動時の 1 回だけしか呼ばれないので
        # in-memory counter で十分。
        monster_counter = 1
        loadout_counter = 1
        # Phase B-2b: spawn_condition が無い (= None / is_always) placement のみ
        # シナリオ起動時に即配置する static 経路。条件付き placement は
        # SpotGraphMonsterSpawnStageService が tick 毎に判定して spawn/despawn する。
        for placement in scenario.monster_placements:
            if placement.spawn_condition is not None and not placement.spawn_condition.is_always:
                continue
            template = next(
                (
                    st.template
                    for st in scenario.monster_templates
                    if st.string_id == placement.template_string_id
                ),
                None,
            )
            if template is None:
                raise ValueError(
                    f"monster placement references unknown template: "
                    f"{placement.template_string_id}"
                )
            spot_int = scenario.id_mapper.get_int("spot", placement.spot_string_id)
            spot_id = SpotId.create(spot_int)
            monster_id = MonsterId(monster_counter)
            world_object_id = WorldObjectId(1_000_000 + monster_counter)
            loadout = SkillLoadoutAggregate.create(
                loadout_id=SkillLoadoutId(loadout_counter),
                owner_id=monster_counter,
                normal_capacity=0,
                awakened_capacity=0,
            )
            skill_loadout_repo.save(loadout)
            monster = MonsterAggregate.reconstitute(
                monster_id=monster_id,
                template=template,
                world_object_id=world_object_id,
                skill_loadout=loadout,
                coordinate=Coordinate(
                    x=placement.coordinate_x,
                    y=placement.coordinate_y,
                    z=placement.coordinate_z,
                ),
                spot_id=spot_id,
                current_tick=WorldTick(0),
            )
            monster_repo.save(monster)
            graph.place_monster(monster_id, spot_id)
            monster_counter += 1
            loadout_counter += 1

    graph.clear_events()
    spot_graph_repo.save(graph)

    world_flag_state = MutableWorldFlagState(
        WorldFlagRegistry.of(*scenario.initial_flags) if scenario.initial_flags else None
    )
    exploration_progress = InMemorySpotExplorationProgressStore()
    from ai_rpg_world.application.player.services.fallen_body_registry import (
        FallenBodyRegistry,
    )
    from ai_rpg_world.application.player.services.departed_position_store import (
        DepartedPositionStore,
    )

    fallen_body_registry = FallenBodyRegistry()
    departed_position_store = DepartedPositionStore()

    movement_service = SpotGraphMovementApplicationService(
        spot_graph_repository=spot_graph_repo,
        player_status_repository=player_status_repo,
        departed_position_store=departed_position_store,
        player_perception_policy=player_perception_policy,
    )
    # PR #1: 動的 loot table を effect_service に注入。
    # シナリオが loot_tables を宣言していなくても LootTableRepository は空で
    # 構築する (GIVE_FROM_LOOT_TABLE を使わなければ無影響)。
    from ai_rpg_world.infrastructure.repository.in_memory_loot_table_repository import (
        InMemoryLootTableRepository,
    )
    from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import (
        LootEntry,
        LootTableAggregate,
    )
    from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId
    loot_table_repo = InMemoryLootTableRepository()
    for lt_def in scenario.loot_tables:
        entries = [
            LootEntry(
                item_spec_id=ItemSpecId.create(loot_entry.item_spec_id),
                weight=loot_entry.weight,
                min_quantity=loot_entry.min_quantity,
                max_quantity=loot_entry.max_quantity,
            )
            for loot_entry in lt_def.entries
        ]
        loot_table_repo.save(LootTableAggregate.create(
            loot_table_id=LootTableId.create(lt_def.table_id),
            entries=entries,
            name=lt_def.name,
        ))
    # effect_service に loot_table_repo を注入。
    from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
        WorldGraphEffectService,
    )
    from ai_rpg_world.domain.world_graph.service.spot_interaction_service import (
        SpotInteractionService,
    )
    _effect_service = WorldGraphEffectService(
        loot_table_repository=loot_table_repo,
        ongoing_condition_resolutions={
            condition.flag: condition.resolution
            for condition in scenario.ongoing_conditions
            if condition.resolution
        },
    )
    _interaction_domain_service = SpotInteractionService(effect_service=_effect_service)
    # PR-F (#710 後続): 看板 (WRITE_PLAYER_TEXT) が object.state に残す書き手名
    # 解決用。scenario.player_spawns はこの時点で確定しているので、
    # interaction_service の構築時に resolver として直接渡せる
    # (event_publisher のような二段構築を避けられる)。
    player_name_map = {spawn.player_id: spawn.name for spawn in scenario.player_spawns}
    from ai_rpg_world.application.world_graph.spot_occupancy import (
        SpotOccupancyScope,
        collect_spot_occupancy,
        format_room_occupancy_display,
    )

    def _room_occupancy_message() -> str:
        """表示盤は生存者と遺体を反応として数え、幽霊は数えない。"""
        return format_room_occupancy_display(
            collect_spot_occupancy(
                graph=spot_graph_repo.find_graph(),
                # ScenarioPlayerSpawn は生の int を持つ。PlayerId に正規化しないと
                # life query の repository lookup が外れ、遺体を生者としても数える。
                player_ids=(PlayerId(int(spawn.player_id)) for spawn in scenario.player_spawns),
                player_life_query=player_life_query,
                scope=SpotOccupancyScope.LIVING_PLAYERS_AND_FALLEN_BODIES,
                fallen_body_registry=fallen_body_registry,
            )
        )

    # 持ちきれなかった品の行き先。付与ヘルパーが必須引数で受けるので、
    # 新しい付与経路を足した人は、書いた瞬間に「溢れをどうするか」を
    # 決めることになる。
    ground_overflow_sink = GroundOverflowSink(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        item_repository=item_repo,
        item_spec_repository=item_spec_repo,
    )
    interaction_service = SpotInteractionApplicationService(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        player_inventory_repository=player_inventory_repo,
        item_repository=item_repo,
        item_spec_repository=item_spec_repo,
        world_flag_state=world_flag_state,
        spot_interaction_service=_interaction_domain_service,
        # Phase G (#3): APPLY_DAMAGE / SATISFY_NEED 等で player_status を mutate
        # するために repo を渡す。これまで None だったため damage_specs が
        # 黙って捨てられていた (廃屋の崩れた梁 / 岩礁の縁 等が flavor 止まり)。
        player_status_repository=player_status_repo,
        player_display_name_resolver=lambda pid: player_name_map.get(
            int(pid), f"プレイヤー({int(pid)})"
        ),
        departed_position_store=departed_position_store,
        player_perception_policy=player_perception_policy,
        item_interaction_registry=scenario.item_interaction_registry,
        room_occupancy_message_provider=_room_occupancy_message,
        overflow_sink=ground_overflow_sink,
    )
    # 対人 interaction。シナリオが player_interactions を宣言していなければ
    # action 名が空の service になり、executor が「この世界では人を対象にした
    # 操作が定義されていません」と名指しで返す (物体経路へ流して無関係な
    # 「オブジェクトが見つからない」を出さない)。
    from ai_rpg_world.application.world_graph.interaction_cooldown_store import (
        InteractionCooldownStore,
    )
    from ai_rpg_world.application.world_graph.player_interaction_application_service import (
        PlayerInteractionApplicationService,
    )
    from ai_rpg_world.application.world_graph.spot_effective_lighting_resolver import (
        SpotEffectiveLightingResolver,
    )
    # 対人行為の再使用間隔。world 局所の状態なので Being ではなく world
    # snapshot に載る (InteractionCooldownSubsystemCodec)。
    interaction_cooldown_store = InteractionCooldownStore()
    player_interaction_service = PlayerInteractionApplicationService(
        spot_graph_repository=spot_graph_repo,
        player_inventory_repository=player_inventory_repo,
        item_repository=item_repo,
        item_spec_repository=item_spec_repo,
        player_status_repository=player_status_repo,
        player_life_query=player_life_query,
        fallen_body_registry=fallen_body_registry,
        world_flag_state=world_flag_state,
        player_interactions=scenario.player_interactions,
        interaction_service=_interaction_domain_service,
        effect_service=_effect_service,
        cooldown_store=interaction_cooldown_store,
        # _current_tick_provider はこの下で定義される。名前解決を呼び出し時
        # まで遅らせる (ここで渡すと NameError)。
        current_tick_provider=lambda: _current_tick_provider(),
        minutes_per_tick=_minutes_per_tick(scenario),
        player_perception_policy=player_perception_policy,
        overflow_sink=ground_overflow_sink,
    )
    # 物体操作の待ち時間も同じ store に載せる。別 store を作ると、長走実験の
    # 再開で物体側だけ待ち時間が消える (design_decisions #27 と同じ形)。
    interaction_service.set_cooldown_store(
        interaction_cooldown_store,
        minutes_per_tick=_minutes_per_tick(scenario),
    )
    exploration_service = SpotExplorationApplicationService(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        player_inventory_repository=player_inventory_repo,
        item_repository=item_repo,
        item_spec_repository=item_spec_repo,
        world_flag_state=world_flag_state,
        exploration_progress_store=exploration_progress,
        overflow_sink=ground_overflow_sink,
    )
    # spot-graph 世界専用の drop/pickup サービス。
    # tile-map 時代の ItemDroppedFromInventoryDropHandler は
    # physical_map 依存で world_runtime では発火しないため、本サービスが
    # SpotInterior.ground_items に直接書き込んで spot-graph 経路で
    # 拾えるようにする。LLM tool 配線とイベント/観測統合はフォロー
    # アップ PR で扱う。
    from ai_rpg_world.application.common.command_scope_factory import CommandScopeFactory
    from ai_rpg_world.application.common.event_delivery import (
        DeliveryChannel,
        DeliveryGuarantee,
    )
    from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
        PlayerDroppedItemEvent,
        PlayerGaveItemEvent,
        PlayerPickedUpItemEvent,
    )
    from ai_rpg_world.infrastructure.events.command_event_dispatcher import (
        CommandEventDispatcher,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_item_transfer_command_repository_provider import (
        InMemoryItemTransferCommandRepositoryProviderFactory,
    )
    from ai_rpg_world.infrastructure.unit_of_work.command_scope_transaction_adapter import (
        InMemoryUnitOfWorkTransactionFactory,
    )

    item_transfer_dispatcher = CommandEventDispatcher()
    for item_transfer_event_type in (
        PlayerDroppedItemEvent,
        PlayerGaveItemEvent,
        PlayerPickedUpItemEvent,
    ):
        item_transfer_dispatcher.register_after_commit(
            item_transfer_event_type,
            lambda event: pipeline_event_publisher.publish_all((event,)),
            channel=DeliveryChannel.OBSERVATION,
            guarantee=DeliveryGuarantee.BEST_EFFORT,
        )
    item_transfer_scope_factory = CommandScopeFactory(
        InMemoryUnitOfWorkTransactionFactory(data_store),
        sync_dispatcher=item_transfer_dispatcher,
        after_commit_handoff=item_transfer_dispatcher,
        repository_provider_factory=(
            InMemoryItemTransferCommandRepositoryProviderFactory(spot_graph_repo)
        ),
    )
    item_transfer_service = SpotGraphItemTransferService(
        spot_graph_repository=spot_graph_repo,
        player_inventory_repository=player_inventory_repo,
        spot_interior_repository=spot_interior_repo,
        item_repository=item_repo,
        player_status_repository=player_status_repo,
        item_transfer_command_scope_factory=item_transfer_scope_factory,
    )
    pending_trade_offer_store = InMemoryPendingTradeOfferStore()
    trade_freeze_service = TradeFreezeService(
        pending_trade_offer_store=pending_trade_offer_store,
        player_inventory_repository=player_inventory_repo,
        player_status_repository=player_status_repo,
        item_repository=item_repo,
    )
    def _observe_expired_trade_offer(offer) -> None:
        """流れた取引を当事者へ知らせる。

        黙って消すと、target からは「さっきまであった選択肢が理由もなく無く
        なった」に見える。offerer にとっても、凍結が解けた理由が分からない。
        """
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
            PlayerTradeOfferEvent,
        )

        graph = spot_graph_repo.find_graph()
        try:
            spot_id = graph.get_entity_spot(
                EntityId.create(int(offer.offerer_player_id))
            )
        except Exception:
            return
        graph.add_event(
            PlayerTradeOfferEvent.create(
                aggregate_id=graph.graph_id,
                aggregate_type="SpotGraphAggregate",
                entity_id=EntityId.create(int(offer.target_player_id)),
                partner_entity_id=EntityId.create(int(offer.offerer_player_id)),
                offerer_entity_id=EntityId.create(int(offer.offerer_player_id)),
                spot_id=spot_id,
                kind="expired",
                gives_text=_describe_trade_side(offer.gives),
                asks_text=_describe_trade_side(offer.asks),
            )
        )
        spot_graph_repo.save(graph)

    trade_offer_expiry_stage = TradeOfferExpiryStage(
        pending_trade_offer_store=pending_trade_offer_store,
        trade_freeze_service=trade_freeze_service,
        expiry_observer=_observe_expired_trade_offer,
    )
    player_trade_service = PlayerTradeService(
        pending_trade_offer_store=pending_trade_offer_store,
        trade_freeze_service=trade_freeze_service,
        spot_graph_repository=spot_graph_repo,
        player_inventory_repository=player_inventory_repo,
        player_status_repository=player_status_repo,
        item_repository=item_repo,
        item_spec_repository=item_spec_repo,
        item_spec_name_resolver=lambda spec_id: _resolve_item_spec_name(spec_id),
        entity_name_resolver=lambda entity_id: _resolve_entity_name(entity_id),
        # 期限は世界の広さで決まるのでシナリオが持つ。書かれていなければ
        # サービス側の既定に任せる (既定値を 2 箇所に置かない)。
        **(
            {"expires_in_ticks": scenario.player_trade_offer_expires_in_ticks}
            if scenario.player_trade_offer_expires_in_ticks is not None
            else {}
        ),
        overflow_sink=refuse_overflow("同席取引の決済"),
    )
    market_board_store = InMemoryMarketBoardStore(
        board_spot_id=scenario.market.board_spot_id if scenario.market else None,
    )
    board_delivery_overflow_sink = GroundOverflowSink(
        # 落とし先を板に固定する。買い手の居場所に依存させないことが、
        # 「探しに行く先が決まる」ことの根拠になる。
        fixed_spot_provider=lambda: market_board_store.board_spot_id,
        event_kind="delivery",
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        item_repository=item_repo,
        item_spec_repository=item_spec_repo,
    )
    market_service = MarketService(
        market_board_store=market_board_store,
        delivery_overflow_sink=board_delivery_overflow_sink,
        # 届く範囲はシナリオの宣言。書かれていなければ場所に縛られたまま。
        reach=scenario.market.reach if scenario.market else MarketReach.AT_SPOT,
        # 板は物理的に置かれた物なので、既定では同席していないと使えない。
        # 判定にグラフが要る (露出判断ではなく実行時の失敗として返す)。
        spot_graph_repository=spot_graph_repo,
        player_inventory_repository=player_inventory_repo,
        player_status_repository=player_status_repo,
        item_repository=item_repo,
        item_spec_repository=item_spec_repo,
        item_spec_name_resolver=lambda spec_id: _resolve_item_spec_name(spec_id),
        entity_name_resolver=lambda entity_id: _resolve_entity_name(entity_id),
        # 期限は世界の広さで決まるのでシナリオが持つ。書かれていなければ
        # サービス側の既定に任せる (既定値を 2 箇所に置かない)。
        **(
            {"expires_in_ticks": scenario.market.order_expires_in_ticks}
            if scenario.market and scenario.market.order_expires_in_ticks is not None
            else {}
        ),
        overflow_sink=refuse_overflow("市場の約定"),
    )
    # 期限を過ぎた注文を毎 tick 片付ける。**これを繋がないと、期限は
    # 宣言されているのに注文が永久に板へ残る** (v3 run で t33 の出品が
    # t80 まで生きていた)。
    market_order_expiry_stage = MarketOrderExpiryStage(market_service=market_service)
    if scenario.market is not None:
        # 板が空だと相場感がゼロから始まり、最初の値付けが当てずっぽうになる。
        # 商人名義で数量有限の注文を置いておくと、売れれば自然に消える。
        for initial_order in scenario.market.initial_orders:
            place = (
                market_service.place_merchant_sell_order
                if initial_order.side == "sell"
                else market_service.place_merchant_buy_order
            )
            place(
                merchant_id=initial_order.merchant_id,
                item_spec_id=initial_order.item_spec_id,
                quantity=initial_order.quantity,
                unit_price=initial_order.unit_price,
                current_tick=0,
                # 注文ごとの寿命。書かれていなければ板ぜんたいの既定に従う。
                expires_in_ticks=initial_order.expires_in_ticks,
            )
    merchant_trade_service = SpotGraphMerchantTradeService(
        spot_graph_repository=spot_graph_repo,
        player_status_repository=player_status_repo,
        player_inventory_repository=player_inventory_repo,
        item_repository=item_repo,
        item_spec_repository=item_spec_repo,
        merchants=scenario.merchants,
        item_spec_name_resolver=lambda spec_id: _resolve_item_spec_name(spec_id),
        # 取引に出している gold と品を、売買からも使えないようにする。
        trade_freeze_service=trade_freeze_service,
        overflow_sink=refuse_overflow("商人との売買"),
    )
    # player_name_map は interaction_service の resolver 用に既に構築済み
    # (上記 SpotInteractionApplicationService 呼び出しの直前)。ここでは
    # 再利用するだけ。

    def _resolve_entity_name(entity_id: int) -> str:
        return player_name_map.get(entity_id, f"プレイヤー({entity_id})")

    # P-U3/P-U4 (停滞感の表出): 自己・他者の両方が共有する 1 本の provider。
    # ``runtime`` / ``runtime._stagnation_pressure_store`` は本関数の後段で
    # 構築される (state_builder は runtime インスタンス生成より前に組み立てる
    # 既存の配線順)。closure は呼び出し時に free variable ``runtime`` を
    # enclosing scope から遅延解決するので、実際に snapshot が build される
    # 時点 (= create_world_runtime 完了後のリクエスト処理中) には
    # ``runtime._aux_being_resolver`` / ``runtime._stagnation_pressure_store``
    # は解決済みになっている。
    #
    # STAGNATION_PRESSURE_ENABLED が OFF のときは
    # ``runtime._stagnation_pressure_store`` が None のままなので、この
    # provider は常に none を返す (= 導入前とプロンプト完全一致)。
    # episodic pipeline 自体が OFF (LLM_EPISODIC_ENABLED=0) で
    # ``_aux_being_resolver`` が未構築の経路も同様に none へ縮退する。
    #
    # 呼び出し対象は自分自身 (P-U3) だけでなく builder の nearby ループが
    # 引く他 player (P-U4) も含むため、関数名は「自己」に限定しない
    # (旧名 ``_resolve_own_stagnation_band`` は誤解を招くため改名した)。
    #
    # store は組めているのに being が未解決 (= resolve_being_id が None) の
    # ケースは、player が being に未 attach 等で正当に起こりうる一方、配線
    # 漏れでも同じ none 縮退になり見分けが付かない。ログが無いと「停滞感が
    # 永久に出ない」を「前進中で count==0」と区別できず、この機能が守りたい
    # 「静かな失敗を弾く」という方針に反するので、player_id ごとに 1 回だけ
    # 診断用の warning を残す (毎 tick 溢れさせないためのスロットル)。
    # store 自体が None (= 機能無効) のときは何も出さない。
    _stagnation_being_unresolved_warned: set[int] = set()

    def _resolve_stagnation_band_for_player(player_id: int) -> str:
        resolver = getattr(runtime, "_aux_being_resolver", None)
        world_id = getattr(runtime, "_aux_being_default_world_id", None)
        store = getattr(runtime, "_stagnation_pressure_store", None)
        if resolver is None or world_id is None or store is None:
            return STAGNATION_PRESSURE_BAND_NONE
        being_id = resolver.resolve_being_id(world_id, PlayerId(player_id))
        if being_id is None:
            if player_id not in _stagnation_being_unresolved_warned:
                _stagnation_being_unresolved_warned.add(player_id)
                logger.warning(
                    "stagnation_band_provider: player_id=%s に attach 済みの "
                    "being が見つからず band は none に縮退する "
                    "(この player については以後再警告しない)",
                    player_id,
                )
            return STAGNATION_PRESSURE_BAND_NONE
        count = store.get_by_being(being_id)
        return resolve_stagnation_pressure_band(count)

    def _resolve_item_state(item_instance_id_value: int) -> Optional[dict]:
        """Phase D-3a: instance_id から state dict を引く軽量 resolver。

        地面アイテムの spoiled 表示用。InMemoryItemRepository.find_by_id は
        dict lookup なので毎 prompt 構築で叩いても問題なし。
        """
        from ai_rpg_world.domain.item.value_object.item_instance_id import (
            ItemInstanceId as _IID,
        )
        item = item_repo.find_by_id(_IID(item_instance_id_value))
        return dict(item.state) if item is not None else None

    def _build_inventory(pid: PlayerId) -> tuple:
        inv = player_inventory_repo.find_by_id(pid)
        if inv is None:
            return ()
        # spec_id 別に集約しつつ「代表 instance」のスロット番号と instance id を覚える。
        # 代表 = 最初に発見したスロットの instance。drop_item ツールが
        # 「I1 = 流木 (x2)」のうち1個を落とすときの target になる。
        # Phase D-3a: spoiled 状態が異なる instance は別エントリにする。
        # 同 spec でも (spec_id, is_spoiled) を集約キーにすることで「生の魚 x2」と
        # 「生の魚 x1 (腐敗)」が並列に出る。腐敗食を腐敗していない食料と混ぜて
        # 表示すると、エージェントが「合計 x3 ある」と誤認するのを防ぐ。
        seen_groups: dict[tuple[int, bool], list] = {}
        for slot_id in range(inv._max_slots):
            from ai_rpg_world.domain.player.value_object.slot_id import SlotId
            iid = inv.get_item_instance_id_by_slot(SlotId(slot_id))
            if iid is None:
                continue
            item = item_repo.find_by_id(iid)
            if item is None:
                continue
            sid = item.item_spec.item_spec_id.value
            is_spoiled = bool(item.state.get("spoiled"))
            key = (sid, is_spoiled)
            if key not in seen_groups:
                name = item.item_spec.name
                item_spec_definition = item_spec_repo.find_by_id(item.item_spec.item_spec_id)
                # 実験 #29 後続: item_type を持ち回って prompt 側で type タグ
                # 表示できるようにする。ItemType.value は "consumable" 等の
                # 小文字列。enum 経由なので未設定リスクはない。
                item_type_value = item.item_spec.item_type.value
                description_value = item.item_spec.description or ""
                usage_hint_value = (
                    (getattr(item_spec_definition, "usage_hint", None) or "")
                    if item_spec_definition is not None
                    else (item.item_spec.usage_hint or "")
                )
                category_value = (
                    str(getattr(item_spec_definition, "category", "") or "")
                    if item_spec_definition is not None
                    else ""
                )
                seen_groups[key] = [
                    name,
                    0,
                    slot_id,
                    iid.value,
                    item_type_value,
                    description_value,
                    usage_hint_value,
                    category_value,
                ]
            seen_groups[key][1] += 1
        return tuple(
            SpotGraphInventoryItemEntry(
                item_spec_id=sid,
                name=info[0],
                quantity=info[1],
                slot_id=info[2],
                item_instance_id=info[3],
                is_spoiled=is_spoiled,
                item_type=info[4],
                description=info[5],
                usage_hint=info[6],
                category=info[7],
            )
            for (sid, is_spoiled), info in seen_groups.items()
        )

    from ai_rpg_world.domain.world.value_object.weather_state import WeatherState
    from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum

    weather_config = scenario.weather_config
    weather_holder = {
        "state": (
            weather_config.initial_state
            if weather_config is not None and weather_config.enabled
            else WeatherState(weather_type=WeatherTypeEnum.FOG, intensity=0.6)
        )
    }

    # 昼夜サイクル (Phase B-1)。シナリオが宣言していなければ None で
    # 「昼夜の概念なし」状態にする (既存 world_runtime / 廃病院は影響なし)。
    day_night_stage: Optional[SpotGraphDayNightStageService] = None
    day_night_config = scenario.day_night_config
    if day_night_config is not None:
        day_night_stage = SpotGraphDayNightStageService(
            cycle=day_night_config.cycle,
        )

    # 光源アイテムを自動検出
    light_source_item_spec_ids = frozenset(
        rm.item_spec_id
        for rm in item_spec_repo.find_all()
        if getattr(rm, "is_light_source", False)
    )

    def _owned_item_spec_ids_provider(entity_id: int) -> frozenset:
        inv = player_inventory_repo.find_by_id(PlayerId(entity_id))
        if inv is None:
            return frozenset()
        return collect_owned_item_spec_ids_from_inventory(inv, item_repo)

    def _build_phase_label_resolver(day_night_config):
        """シナリオが宣言した昼夜フェーズから「名前 → 呼び名」の解決器を作る。

        宣言が無い (昼夜サイクルを使わない世界) なら None を返し、時刻帯ヒントは
        出ない。**コード側に既定の呼び名を持たない**のが要点。持つと
        `world_briefing` が直した「写しは腐る」と同じことが起きる。実際に腐って
        いた: v3_coop / v4_coop が `predawn`(未明) を宣言しているのに、コード側の
        表は `morning / noon / afternoon / evening / night` だった。
        """
        if day_night_config is None:
            return None
        labels = {
            phase.name: phase.display_text
            for phase in day_night_config.cycle.phases
            if phase.display_text
        }
        return labels.get if labels else None

    def _build_monster_view_provider_for_runtime(_monster_repo):
        """state_builder に渡す monster_view_provider を遅延構築する小ヘルパ。

        spot_graph_monster_view.build_monster_view_provider を呼ぶだけだが、
        circular import を避けるために関数内 import に寄せた。
        """
        from ai_rpg_world.application.world_graph.spot_graph_monster_view import (
            build_monster_view_provider,
        )
        return build_monster_view_provider(_monster_repo)

    def _describe_trade_side(side) -> str:
        """取引の片側を、人が読める短い形にする。"""
        parts = [
            f"{_resolve_item_spec_name(spec_id)} {quantity}つ"
            for spec_id, quantity in side.items
        ]
        if side.gold:
            parts.append(f"{side.gold}G")
        return "・".join(parts) if parts else "なし"

    def _incoming_trade_offers_for(player_id: int) -> tuple:
        """その人に来ている申し出を、表示用の形にして返す。"""
        from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
            SpotGraphTradeOfferEntry,
        )

        current = time_provider.get_current_tick().value
        return tuple(
            SpotGraphTradeOfferEntry(
                offerer_name=_resolve_entity_name(int(offer.offerer_player_id)),
                gives_text=_describe_trade_side(offer.gives),
                asks_text=_describe_trade_side(offer.asks),
                remaining_ticks=max(0, offer.expires_at_tick - current),
            )
            for offer in pending_trade_offer_store.list_for_target(PlayerId(player_id))
        )

    def _resolve_item_spec_name(spec_id_value: int) -> str:
        """item_spec_id → 表示名解決。地面アイテムの prompt 表示などで使う。"""
        from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId as _ISpecId
        spec_union = item_spec_repo.find_by_id(_ISpecId.create(spec_id_value))
        if spec_union is None:
            return ""
        spec = spec_union.to_item_spec() if hasattr(spec_union, "to_item_spec") else spec_union
        return spec.name

    def _observe_visible_monster_for_player(player_id: int, entry: Any) -> None:
        """初めて見た monster を observation として player に届ける。

        current state の常時表示とは別に、入室時に初めて目に入った質感を
        episode へ流すための hook。Encounter Memory で一度きりにし、
        追加の per-player store は増やさない。
        """
        key = EncounterKey(kind="object", identifier=f"monster_{entry.monster_id}")
        pid = PlayerId(player_id)
        if encounter_memory.lookup(pid, key) is not None:
            return
        encounter_memory.observe(pid, key, _current_tick_provider())
        appearance = str(getattr(entry, "appearance", "") or "").strip()
        appearance_suffix = f" {appearance}" if appearance else ""
        output = ObservationOutput(
            prose=(
                f"{entry.display_name}が同じ場所にいることに気づいた。"
                f"{appearance_suffix}"
            ).strip(),
            structured={
                "type": "monster_encountered",
                "monster_id": int(entry.monster_id),
                "display_name": str(entry.display_name),
                "appearance": appearance,
            },
            observation_category="environment",
            schedules_turn=True,
            breaks_movement=False,
        )
        runtime._emit_observation_directly(pid, output)

    def _observe_fallen_body_for_player(
        player_id: int, victim_entity_id: int, victim_name: str, is_dead: bool
    ) -> None:
        """初めて見た「倒れている人」を observation として届ける。

        **同席者行に出ているだけでは、気づいた瞬間が無い。** 行は毎 tick
        そこにある「見えている状態」で、観測は一度きりの「気づいた瞬間」。
        観測が無いと ``schedules_turn`` が立たないので、**死体の前を素通り
        する**。run 008 でクルーが 2 人殺されても通報が起きなかった直接の
        原因がこれ。

        一度きりの判定は Encounter Memory を使い、per-Being store を増やさ
        ない (monster の初回観測と同じ形)。増やすと snapshot への追従が要る
        (CLAUDE.md #27)。

        倒れているだけの相手と死んでいる相手を同じ key にする。**同じ人の
        体を二度「見つける」ことは無い**。蘇生されて再び倒れた場合も、
        既に一度見ているので驚きは薄い。

        暗さは見ない。同席者行が暗所でも死体を出しているので、ここだけ
        隠すと行と観測が食い違う。
        """
        if int(player_id) == int(victim_entity_id):
            return
        key = EncounterKey(kind="body", identifier=f"player_{victim_entity_id}")
        pid = PlayerId(player_id)
        if encounter_memory.lookup(pid, key) is not None:
            return
        encounter_memory.observe(pid, key, _current_tick_provider())
        name = victim_name or "誰か"
        prose = (
            f"{name}が倒れているのを見つけた。動かない。"
            if is_dead
            else f"{name}が倒れているのを見つけた。"
        )
        # cue が読むのは int の spot_id_value。get_player_spot_id は trace 用の
        # 文字列を返すので使えない。
        body = runtime._fallen_body_registry.find(PlayerId(int(victim_entity_id)))
        spot_id_value = int(body.spot_id) if body is not None else None
        structured = {
            "type": "fallen_body_found",
            # actor / spot_id_value は episodic cue が読む key。ここを外すと
            # 「誰の」「どこで」が記憶の索引に乗らない。
            "actor": name,
            "is_dead": bool(is_dead),
        }
        if spot_id_value is not None:
            structured["spot_id_value"] = spot_id_value
        runtime._emit_observation_directly(
            pid,
            ObservationOutput(
                prose=prose,
                structured=structured,
                observation_category="social",
                schedules_turn=True,
                # 死体を見つけたら足は止まる。移動を続けるほうが不自然。
                breaks_movement=True,
            ),
        )

    # PR #2 状態異常 surface: 残り tick 表示のため current_tick_provider を
    # state_builder に渡す。time_provider 自体の構築は下方なので、ここでは
    # ホルダー経由で遅延参照する (構築順を入れ替えると他依存が崩れるため)。
    _time_provider_holder: dict[str, Any] = {}

    def _current_tick_provider() -> int:
        tp = _time_provider_holder.get("provider")
        if tp is None:
            return 0
        return tp.get_current_tick().value

    # 相互に役割を知る者どうしの関係は、役割名ではなく真偽へ畳んでから
    # prompt の状態組み立てへ渡す。これにより「同じ側」と表示した相手への
    # 必ず失敗する襲撃候補を消しつつ、raw の role 語彙を表示層へ持ち込まない。
    _role_by_player_id = {
        int(spawn.player_id): str(spawn.initial_state.get("role") or "")
        for spawn in scenario.player_spawns
    }
    _mutually_known_roles = frozenset(scenario.mutually_known_roles)

    def _is_known_ally(actor_player_id: PlayerId, target_player_id: PlayerId) -> bool:
        actor_role = _role_by_player_id.get(int(actor_player_id), "")
        return bool(
            actor_role in _mutually_known_roles
            and _role_by_player_id.get(int(target_player_id), "") == actor_role
        )

    state_builder = SpotGraphCurrentStateBuilder(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        player_status_repository=player_status_repo,
        fallen_body_registry=fallen_body_registry,
        player_perception_policy=player_perception_policy,
        departed_position_store=departed_position_store,
        entity_name_resolver=_resolve_entity_name,
        inventory_builder=_build_inventory,
        weather_provider=lambda: weather_holder["state"],
        world_flags_provider=world_flag_state.as_frozen_set,
        light_source_item_spec_ids=light_source_item_spec_ids,
        owned_item_spec_ids_provider=_owned_item_spec_ids_provider,
        item_spec_name_resolver=_resolve_item_spec_name,
        time_of_day_provider=(
            day_night_stage.current_time_of_day
            if day_night_stage is not None
            else None
        ),
        monster_view_provider=(
            _build_monster_view_provider_for_runtime(monster_repo)
            if scenario.monster_placements
            else None
        ),
        # Phase D-3a: 地面アイテムの spoiled 表示。instance_id から state dict を
        # 引く軽量 resolver。InMemoryItemRepository.find_by_id は dict lookup なので
        # 毎 prompt 構築で叩いても問題なし。
        item_state_resolver=_resolve_item_state,
        current_tick_provider=_current_tick_provider,
        minutes_per_tick=_minutes_per_tick(scenario),
        stagnation_band_provider=_resolve_stagnation_band_for_player,
        areas=scenario.areas,
        distant_cues=scenario.distant_cues,
        # 経済統合 Phase 1: 商人の宣言。空なら商人節も所持金行も出ない
        # (宣言していない世界の prompt を 1 文字も変えない)。
        merchants=scenario.merchants,
        # 板の品揃えを「現在の状況」に出すために要る。
        market_service=market_service,
        # 自分宛ての申し出を状況確認へ出す。accept / decline は常時露出なので、
        # 見えていないと受けようがない。
        incoming_trade_offers_provider=_incoming_trade_offers_for,
        distant_view_trace_enabled=config.distant_view_trace_enabled,
        trace_recorder_provider=lambda: getattr(runtime, "_trace_recorder", None),
        visible_monster_observer=_observe_visible_monster_for_player,
        fallen_body_observer=_observe_fallen_body_for_player,
        # 同席者行に「この相手に何ができるか」を出す。出さないと対人行為は
        # 宣言されていても LLM から発見できない。
        #
        # 渡すのは物体・持ち物と共通の構造化 entry。選べる操作と現在阻害中の
        # 操作を UI 側の同じ整形関数で二段に分ける。executor の「使える操作」
        # 列挙は識別子が要るので、そちらは
        # ``available_action_names`` を使い続ける
        # (world_runtime.available_player_action_names)。
        player_action_entries_provider=(
            player_interaction_service.available_action_entries_for
        ),
        known_ally_checker=_is_known_ally,
        # 組み込みツールを行に宣伝する前に、この世界に在るかを訊く。
        # 訊かずに出していたため、`disabled_tools` で消したはずの
        # tend_to_player が死体の行に並び続けていた。
        is_tool_exposed=lambda name: runtime.tool_exposure.is_exposed(name),
        state_display_names=build_own_state_display_names(
            list(scenario.graph.iter_spot_nodes()),
            scenario.interiors,
            metadata.role_labels,
        ),
        # 手番を記録する効果が書く本人 state の key を、宣言から導出して伏せる。
        # 物体 state と同じ判断 (書く宣言があるなら出さない)。名前を当てにいく
        # 形には戻さない。
        hidden_player_state_keys=build_recorded_player_state_tick_keys(
            list(scenario.graph.iter_spot_nodes()),
            scenario.interiors,
            scenario.player_interactions,
        ),
        # 変えられない属性を注記へ届ける。宣言の無い世界では空なので、
        # prompt は 1 ビットも変わらない。
        player_attribute_specs=scenario.player_attribute_specs,
        item_interaction_registry=scenario.item_interaction_registry,
    )
    # 物体操作の待ち時間を行に添える。#964 で対人行に足したのと同じ判断で、
    # 待ちが見えないと「選べるのに必ず失敗する手」になる (#860)。
    state_builder.set_object_cooldown_hint_provider(
        lambda player_id, object_id, interaction: (
            interaction_service.cooldown_wait_hint(
                player_id, object_id, interaction, _current_tick_provider()
            )
        )
    )
    state_builder.set_item_cooldown_hint_provider(
        lambda player_id, item_spec_id, interaction: (
            interaction_service.item_cooldown_wait_hint(
                player_id, item_spec_id, interaction, _current_tick_provider()
            )
        )
    )

    # ── 観測パイプライン構築 ──
    # Issue #227 PR-5 (tile-map 除去): physical_map_repository=None で resolver を
    # 組み立てる。tile-map 依存の strategy (Pursuit / Monster / Combat / Harvest /
    # Default の世界座標フォールバック) は world_runtime では関連 event が発火しないため
    # inert で、resolver 内部の NullWorldObjectToPlayerResolver で安全に処理される。
    # PlayerSpokeEvent は SpotGraphSpeechRecipientStrategy (hop-based) で処理される。
    #
    # WARN: 将来 tile-map ベースの event (Pursuit/Monster/Combat/Harvest 等) を
    # world_runtime に持ち込む場合は、physical_map_repository を実装した上で渡す必要がある。
    obs_resolver = create_observation_recipient_resolver(
        player_status_repository=player_status_repo,
        player_life_query=player_life_query,
        player_perception_policy=player_perception_policy,
        departed_position_store=departed_position_store,
        physical_map_repository=None,
        spot_graph_repository=spot_graph_repo,
    )

    # #356 後続: monster_repository を渡さないと name_resolver が
    # FALLBACK_MONSTER_LABEL ("何かのモンスター") を返してしまい、攻撃観測
    # 全件が「何かのモンスターに襲われ…」になっていた (内部 fallback の漏出)。
    # シナリオで monster_placements が宣言されているなら必ず注入する。
    # #356 後続 (#26 experiment) 追加: spot_interior_repository を渡さないと
    # `_resolve_object_name` が "何か" fallback に落ちて
    # "リオが何かのsearchを試みた" のような object placeholder 漏出が
    # 失敗観測 prose に出ていた (#373 経路で 92/92 件)。
    # player_downed の第三者観測と対人 interaction の宣言文が、同じ実効照明と
    # 同じ身元開示規則を見る。観測 formatter の構築前に 1 度だけ作り、下で
    # interaction service にも同じ instance を配線する。
    _effective_lighting_resolver = SpotEffectiveLightingResolver(
        spot_graph_repository=spot_graph_repo,
        entity_has_light_source=lambda entity_id: bool(
            light_source_item_spec_ids
            & _owned_item_spec_ids_provider(entity_id)
        ),
        time_of_day_provider=(
            day_night_stage.current_time_of_day
            if day_night_stage is not None
            else None
        ),
        weather_provider=lambda: weather_holder.get("state"),
    )
    obs_formatter = ObservationFormatter(
        death_semantics=scenario.death_semantics,
        spot_graph_repository=spot_graph_repo,
        monster_repository=monster_repo if scenario.monster_placements else None,
        spot_interior_repository=spot_interior_repo,
        departed_position_store=departed_position_store,
        departed_player_checker=player_perception_policy.is_departed,
        downed_self_becomes_departed=(
            scenario.departed_agents_enabled
            and scenario.death_semantics.grace_ticks == 0
        ),
        effective_lighting_resolver=_effective_lighting_resolver,
    )
    obs_formatter._name_resolver.player_name = lambda pid: player_name_map.get(  # type: ignore[assignment]
        pid.value, f"プレイヤー({pid.value})"
    )

    obs_pipeline = ObservationPipeline(
        resolver=obs_resolver,
        formatter=obs_formatter,
        player_status_repository=player_status_repo,
    )
    recent_event_store = UnifiedRecentEventStore()
    obs_buffer = DefaultObservationContextBuffer(event_store=recent_event_store)
    # PR #451 (PR 6/6): 短期記憶を「全部揃ってから 1 回 build」式に統合。
    # LLM 経路 (summary_service / long_summary_service / persona_resolver) は
    # 旧来 setter で後注入していたが、ctor 注入に統一して呼び忘れ silent failure
    # を構造で排除。trace_recorder / current_tick は runtime instance に依存する
    # ため別経路 (set_trace_recorder) で差し替え (NullObject 経由で安全)。
    short_term_memory = _build_short_term_memory(
        config,
        scenario=scenario,
        world_character=world_character,
        persona_block=persona_block,
        event_store=recent_event_store,
    )
    action_result_store = DefaultActionResultStore(event_store=recent_event_store)
    # encounter_memory は上 (spawn loop 直前) で生成済 (PR4)。

    class _RuntimeTravelContext(SpotGraphTravelContextProvider):
        def __init__(
            self,
            player_inventory_repository: InMemoryPlayerInventoryRepository,
            item_repository: InMemoryItemRepository,
            world_flag_state: MutableWorldFlagState,
        ) -> None:
            self._player_inventory_repository = player_inventory_repository
            self._item_repository = item_repository
            self._world_flag_state = world_flag_state

        def owned_item_spec_ids_for(self, player_id: PlayerId) -> FrozenSet[ItemSpecId]:
            inv = self._player_inventory_repository.find_by_id(player_id)
            if inv is None:
                return frozenset()
            return collect_owned_item_spec_ids_from_inventory(inv, self._item_repository)

        def world_flags(self) -> FrozenSet[str]:
            return self._world_flag_state.as_frozen_set()

    travel_context = _RuntimeTravelContext(
        player_inventory_repository=player_inventory_repo,
        item_repository=item_repo,
        world_flag_state=world_flag_state,
    )
    travel_stage = SpotGraphTravelStageService(
        player_status_repository=player_status_repo,
        movement_service=movement_service,
        travel_context=travel_context,
    )
    travel_stage.set_departed_checker(player_perception_policy.is_departed)

    scenario_event_progress = InMemorySpotGraphScenarioEventProgressStore()
    # GAME_PHASE_IS と WorldRuntime が同じ状態を見るよう、GamePhaseStore は
    # factory 内で 1 度だけ構築して共有する。別々に作ると会議遷移が条件評価へ
    # 届かず、条件が永久に偽になる。
    game_phase_store = GamePhaseStore(
        meeting_tick_limit=scenario.meeting_tick_limit,
        meeting_silence_limit_ticks=scenario.meeting_silence_limit_ticks,
        meeting_cooldown_ticks=scenario.meeting_cooldown_ticks,
        emergency_buttons_per_player=scenario.emergency_buttons_per_player,
    )
    # 評価器は scenario_event_stage と reactive_binding_stage で共有する。
    # weather_state_provider を渡すことで WEATHER_IS 条件が解ける。
    # Phase D-1: PROBABILITY 条件評価用の random.Random を注入する。
    # 実験設定に scenario_random_seed があれば seed 注入で再現性を確保、
    # 無ければ非決定的 (デフォルト random.Random()) で運用する。
    _scenario_random = (
        random.Random(config.scenario_random_seed)
        if config.scenario_random_seed is not None
        else random.Random()
    )
    condition_evaluator = ScenarioConditionEvaluator(
        world_flag_state=world_flag_state,
        spot_interior_repository=spot_interior_repo,
        player_status_repository=player_status_repo,
        player_inventory_repository=player_inventory_repo,
        item_repository=item_repo,
        weather_state_provider=lambda: weather_holder["state"],
        game_phase_provider=lambda: game_phase_store.current.phase,
        random_source=_scenario_random,
    )
    # recorder は runtime 構築後にも差し替えられるため、値を固定せず実行時に
    # 解決する。同じ評価結果を判定と trace に使い、確率条件を再評価しない。
    predicate_trace_emitter = ScenarioPredicateTraceEmitter(
        lambda: getattr(runtime, "_trace_recorder", None)
    )
    scenario_event_stage = SpotGraphScenarioEventStageService(
        scenario_events=scenario.scenario_events,
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        player_status_repository=player_status_repo,
        player_inventory_repository=player_inventory_repo,
        item_repository=item_repo,
        item_spec_repository=item_spec_repo,
        world_flag_state=world_flag_state,
        progress_store=scenario_event_progress,
        condition_evaluator=condition_evaluator,
        predicate_trace_emitter=predicate_trace_emitter,
        effect_service=_effect_service,
        overflow_sink=ground_overflow_sink,
    )
    reactive_binding_stage = ReactivePassageBindingStageService(
        bindings=scenario.reactive_passage_bindings,
        spot_graph_repository=spot_graph_repo,
        condition_evaluator=condition_evaluator,
        predicate_trace_emitter=predicate_trace_emitter,
    )
    reactive_object_state_stage = ReactiveObjectStateBindingStageService(
        bindings=scenario.reactive_object_state_bindings,
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        condition_evaluator=condition_evaluator,
        predicate_trace_emitter=predicate_trace_emitter,
    )
    sync_action_registry = SynchronizedActionRegistry(world_flag_state)
    sync_resolver_stage = SynchronizedActionResolverStageService(
        groups=scenario.synchronized_action_groups,
        registry=sync_action_registry,
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        world_flag_state=world_flag_state,
        effect_service=_effect_service,
        on_message=lambda group_id, outcome, recipients, message: (
            runtime._append_synchronized_action_observation(
                group_id,
                outcome,
                recipients,
                message,
            )
        ),
    )
    environment_stage = SpotGraphEnvironmentStageService(
        weather_state_provider=lambda: weather_holder["state"],
        weather_state_setter=lambda s: weather_holder.__setitem__("state", s),
        update_interval_ticks=(
            weather_config.update_interval_ticks
            if weather_config is not None and weather_config.enabled
            else 6
        ),
        on_weather_changed=None,
    )
    time_provider = InMemoryGameTimeProvider(initial_tick=0)
    # PR #2 状態異常 surface: state_builder の current_tick_provider が
    # 参照する holder を埋める。
    _time_provider_holder["provider"] = time_provider
    sim_llm_trigger: ILlmTurnTrigger = (
        llm_turn_trigger
        if llm_turn_trigger is not None
        else WorldStandaloneNoopLlmTurnTrigger()
    )
    # tick 経過で空腹 / 疲労が緩やかに増加するステージ。survival_island のような
    # 長期サバイバルでは生存圧の本体になる。world_runtime v1 (廃病院) でも
    # 120 tick の間に空腹 100% に到達するが現状の lose 条件は tick_limit のみ
    # なので挙動に大きな影響はない。
    #
    # HUNGER=max のプレイヤーへ与える毎 tick の飢餓ダメージは、結果判定とは
    # 独立した needs 機構の宣言から取る。無宣言の世界では 0 で無効。
    from ai_rpg_world.domain.player.value_object.agent_need import NeedType

    needs_config = scenario.needs_config
    starvation_dmg = needs_config.starvation_damage_per_tick
    needs_decay_stage = SpotGraphNeedsDecayStageService(
        player_status_repository=player_status_repo,
        starvation_damage_per_tick=starvation_dmg,
        # 空腹と疲労の進み方もシナリオの宣言から取る。**ここで渡し忘れると、
        # 宣言しても既定のまま進む** = 変えたつもりで変わっていない run に
        # なるので、宣言が実際に効くところまでを試験で見ている。
        rates={
            NeedType.HUNGER: needs_config.hunger_per_tick,
            NeedType.FATIGUE: needs_config.fatigue_per_tick,
        },
        # event_publisher は runtime 構築後に pipeline_event_publisher が用意
        # されてから setter 経由で注入する (順序依存を解消するため後付け)。
    )

    # PR #2: 状態異常 tick 進行 stage。active_effects の継続効果適用 + 期限
    # 切れ掃除を担う。event_publisher は後付け bind。
    from ai_rpg_world.application.world_graph.status_effects_tick_stage_service import (
        StatusEffectsTickStageService,
    )
    status_effects_stage = StatusEffectsTickStageService(
        player_status_repository=player_status_repo,
    )

    # Phase B-2a: モンスター攻撃のオーケストレーターと behavior tick service。
    # placements が空ならどちらも構築しないことで、既存シナリオ
    # (廃病院 等) の挙動を一切変えない。
    monster_attack_orchestrator = None
    monster_behavior_service = None
    monster_behavior_stage = None
    monster_spawn_stage = None  # Phase B-2b: 条件付き placement の動的 spawn
    if scenario.monster_placements:
        from ai_rpg_world.application.world_graph.spot_attack_orchestrator import (
            SpotAttackOrchestrator,
        )
        from ai_rpg_world.application.monster.services.spot_monster_behavior_tick_service import (
            SpotMonsterBehaviorTickService,
        )

        monster_attack_orchestrator = SpotAttackOrchestrator(
            spot_graph_repository=spot_graph_repo,
            monster_repository=monster_repo,
            player_status_repository=player_status_repo,
            # PR-K: event_publisher は runtime 構築後に pipeline_event_publisher
            # が用意されてから setter で後付け注入する (= needs_decay_stage
            # 等と同じ pattern)。bind 前は致命攻撃で events が積まれても publish
            # されない (= 旧挙動互換)。
        )
        monster_behavior_service = SpotMonsterBehaviorTickService(
            spot_graph_repository=spot_graph_repo,
            monster_repository=monster_repo,
            player_status_repository=player_status_repo,
            attack_orchestrator=monster_attack_orchestrator,
            world_flags_provider=world_flag_state.as_frozen_set,
            spot_interior_repository=spot_interior_repo,
        )

        # SpotGraphSimulationApplicationService の tick stage は run(tick) を
        # 要求するが behavior service は tick(tick) を持つ。薄いアダプタで橋渡し。
        class _MonsterBehaviorTickStageAdapter:
            def __init__(self, service):
                self._service = service

            def run(self, tick) -> None:
                self._service.tick(tick)

        monster_behavior_stage = _MonsterBehaviorTickStageAdapter(monster_behavior_service)

        # Phase B-2b: 条件付き placement (spawn_condition が is_always でない)
        # に対する動的 spawn / despawn stage。static placement (B-2a 経路) で
        # 既に置いたインスタンスは触らず、条件付き placement だけを動かす。
        conditional_placements = [
            p for p in scenario.monster_placements
            if p.spawn_condition is not None and not p.spawn_condition.is_always
        ]
        if conditional_placements:
            from ai_rpg_world.application.world_graph.spot_graph_monster_spawn_stage_service import (
                MonsterSpawnSlot,
                SpotGraphMonsterSpawnStageService,
            )

            slots = []
            for i, placement in enumerate(conditional_placements):
                template = next(
                    (
                        st.template
                        for st in scenario.monster_templates
                        if st.string_id == placement.template_string_id
                    ),
                    None,
                )
                if template is None:
                    raise ValueError(
                        f"monster placement references unknown template: "
                        f"{placement.template_string_id}"
                    )
                spot_int = scenario.id_mapper.get_int("spot", placement.spot_string_id)
                slot_key = (
                    f"{placement.template_string_id}@{placement.spot_string_id}#{i}"
                )
                slots.append(MonsterSpawnSlot(
                    slot_key=slot_key,
                    template=template,
                    spot_id=SpotId.create(spot_int),
                    coordinate=Coordinate(
                        x=placement.coordinate_x,
                        y=placement.coordinate_y,
                        z=placement.coordinate_z,
                    ),
                    day_night_phase_names=placement.spawn_condition.day_night_phase_names,
                    required_flags=placement.spawn_condition.required_flags,
                    forbidden_flags=placement.spawn_condition.forbidden_flags,
                    weather_type_names=placement.spawn_condition.weather_type_names,
                ))

            monster_spawn_service = SpotGraphMonsterSpawnStageService(
                slots=tuple(slots),
                monster_repository=monster_repo,
                skill_loadout_repository=skill_loadout_repo,
                spot_graph_repository=spot_graph_repo,
                time_of_day_provider=(
                    day_night_stage.current_time_of_day
                    if day_night_stage is not None
                    else None
                ),
                flags_provider=world_flag_state.as_frozen_set,
                weather_type_provider=lambda: (
                    weather_holder["state"].weather_type.name
                    if weather_holder.get("state") is not None
                    else None
                ),
            )
            monster_spawn_stage = monster_spawn_service

    # ── Phase D-2: 食料腐敗ステージ ──
    # spoils_after_ticks が指定された ItemSpec を集約して FoodSpoilageStage を組み立てる。
    # 1 つも無ければ None のままで stage は走らない (= 既存シナリオに無影響)。
    food_spoilage_stage = None
    spoilable_specs: Dict[ItemSpecId, int] = {}
    for item_def in scenario.item_spec_definitions:
        if item_def.spoils_after_ticks is not None:
            spoilable_specs[item_def.spec_id] = item_def.spoils_after_ticks
    if spoilable_specs:
        from ai_rpg_world.application.world_graph.food_spoilage_stage_service import (
            FoodSpoilageStageService,
        )

        def _spec_name_lookup(spec_id: ItemSpecId) -> str:
            spec = item_spec_repo.find_by_id(spec_id)
            return spec.name if spec is not None else ""

        food_spoilage_stage = FoodSpoilageStageService(
            item_repository=item_repo,
            spoilable_specs=spoilable_specs,
            spec_name_lookup=_spec_name_lookup,
            # 観測 callback は runtime construction 後にバインド (runtime 参照が必要)
        )

    # ── Phase E-3: 個別 outcome registry を simulation 前に作る ──
    # runtime に依存しない pure object なので、配線順は publisher より早くて
    # 構わない。registry 自体を player_outcome_rule_stage が必要とする。
    # 後段で PipelineEventPublisher + handler を bind し、broadcast callback も追加する。
    from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
    from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
    # 同 spot の DEAD (終局・復活不可) player を「(死亡している)」と区別表示する
    # ため、DEAD 判定を state_builder に配線する。state_builder は outcome_registry
    # より先に構築されるので、構築時ではなく setter で後付けする。
    state_builder.set_dead_player_checker(
        lambda pid: outcome_registry.get_outcome(pid).is_eliminated
    )
    travel_stage.set_eliminated_checker(
        lambda pid: outcome_registry.get_outcome(pid).is_eliminated
    )
    item_transfer_service.set_player_outcome_registry(outcome_registry)

    # Issue #621: ダウン → DEAD の 30 tick 猶予機構。
    # grace_timer は PlayerDownedEvent handler (= pending 登録) と
    # PlayerRevivedEvent handler (= pending 削除) の両方から触られる。
    # death_grace_stage は tick 毎に grace_ticks 経過判定して DEAD 確定する。
    # outcome_registry 直後に作って、simulation_service にも handler にも
    # 同じ instance を共有させる。
    from ai_rpg_world.application.player.services.player_death_grace_timer import (
        PlayerDeathGraceTimer,
    )
    from ai_rpg_world.application.player.services.player_death_grace_tick_stage import (
        PlayerDeathGraceTickStage,
    )
    death_grace_timer = PlayerDeathGraceTimer()
    death_grace_stage = PlayerDeathGraceTickStage(
        outcome_registry=outcome_registry,
        grace_timer=death_grace_timer,
        # シナリオが宣言していればそれを使う。0 を許すのは「殺したら死ぬ」
        # 世界のため。書き忘れと 0 を区別するため、既定は None で持っている。
        grace_ticks=(
            scenario.death_semantics.grace_ticks
            if scenario.death_semantics.grace_ticks is not None
            else PlayerDeathGraceTickStage.DEFAULT_GRACE_TICKS
        ),
    )

    # プレイヤー個別 outcome の規則は scenario_event と同じ条件評価器・進捗
    # store を使う。規則の発火済み状態も既存 snapshot codec に一緒に載るため、
    # 再開後に一度限りの救助機会が再発火しない。
    player_outcome_rule_stage = None
    if scenario.player_outcome_rules:
        from ai_rpg_world.application.world_graph.player_outcome_rule_stage_service import (
            PlayerOutcomeRuleStageService,
        )

        player_outcome_rule_stage = PlayerOutcomeRuleStageService(
            rules=scenario.player_outcome_rules,
            outcome_registry=outcome_registry,
            condition_evaluator=condition_evaluator,
            progress_store=scenario_event_progress,
            graph_provider=lambda: spot_graph_repo.find_graph(),
            player_ids=[PlayerId(spawn.player_id) for spawn in scenario.player_spawns],
            predicate_trace_emitter=predicate_trace_emitter,
        )

    simulation_service = SpotGraphSimulationApplicationService(
        time_provider=time_provider,
        travel_stage=travel_stage,
        scenario_event_stage=scenario_event_stage,
        reactive_binding_stage=reactive_binding_stage,
        reactive_object_state_stage=reactive_object_state_stage,
        sync_action_resolver_stage=sync_resolver_stage,
        environment_stage=environment_stage,
        day_night_stage=day_night_stage,
        needs_decay_stage=needs_decay_stage,
        monster_spawn_stage=monster_spawn_stage,
        monster_behavior_stage=monster_behavior_stage,
        food_spoilage_stage=food_spoilage_stage,
        status_effects_stage=status_effects_stage,
        player_outcome_rule_stage=player_outcome_rule_stage,
        death_grace_stage=death_grace_stage,
        trade_offer_expiry_stage=trade_offer_expiry_stage,
        market_order_expiry_stage=market_order_expiry_stage,
        llm_turn_trigger=sim_llm_trigger,
        # PR-N: tick stage で graph に積まれた events を heartbeat tick でも
        # observation pipeline 経由で flush する。これが無いと monster_behavior
        # 系の MonsterAteGroundItemEvent / MonsterFeltTemperatureDiscomfort 等
        # が「次に interaction/speech が来るまで遅延」または「永遠に届かない」
        # silent failure になる。
        # runtime はまだ未代入なので lambda で lazy bind する (= 呼出時に
        # 名前解決される)。runtime = WorldRuntime(...) が直後で実行される
        # 順序になっており、tick 開始までには確実に bound される。
        graph_event_flusher=lambda: (
            runtime._process_graph_events(),
            runtime._evaluate_distant_cue_appearances(),
        ),
    )

    runtime = WorldRuntime(
        scenario=scenario,
        _meeting_enabled=scenario.meeting_enabled,
        _interaction_cooldown_store=interaction_cooldown_store,
        _game_phase_store=game_phase_store,
        _spot_graph_repo=spot_graph_repo,
        _spot_interior_repo=spot_interior_repo,
        _player_status_repo=player_status_repo,
        _player_life_query=player_life_query,
        _player_perception_policy=player_perception_policy,
        _fallen_body_registry=fallen_body_registry,
        _departed_position_store=departed_position_store,
        _player_inventory_repo=player_inventory_repo,
        _item_repo=item_repo,
        _item_spec_repo=item_spec_repo,
        _world_flag_state=world_flag_state,
        _effect_service=_effect_service,
        _exploration_progress=exploration_progress,
        _movement_service=movement_service,
        _interaction_service=interaction_service,
        _player_interaction_service=player_interaction_service,
        _exploration_service=exploration_service,
        _item_transfer_service=item_transfer_service,
        _merchant_trade_service=merchant_trade_service,
        _pending_trade_offer_store=pending_trade_offer_store,
        _trade_freeze_service=trade_freeze_service,
        _player_trade_service=player_trade_service,
        _market_board_store=market_board_store,
        _market_service=market_service,
        _ground_overflow_sink=ground_overflow_sink,
        _state_builder=state_builder,
        _game_end_evaluator=GameEndConditionEvaluator(),
        _formatter=SpotGraphCurrentStateFormatter(),
        # PR4: encounter familiarity 注記を【現在地と周囲】に出す。lambda は
        # runtime instance を closure する (= runtime.current_tick / id_mapper
        # は instance method なので、factory function 完了時に bind 済)。
        _ui_context_builder=SpotGraphUiContextBuilder(
            encounter_memory=encounter_memory,
            current_tick_provider=lambda: runtime.current_tick(),
            spot_str_id_resolver=lambda spot_int: scenario.id_mapper.get_str(
                "spot", spot_int
            ),
        ),
        _obs_pipeline=obs_pipeline,
        _obs_buffer=obs_buffer,
        _recent_event_store=recent_event_store,
        _short_term_memory=short_term_memory,
        _action_result_store=action_result_store,
        _encounter_memory=encounter_memory,
        # PR #448 (PR 3/6): cfg.prompt_section_order を使う (= env を再読しない)
        _context_strategy=_build_context_format_strategy_from_config(config),
        _time_provider=time_provider,
        _simulation_service=simulation_service,
        _travel_stage=travel_stage,
        _player_outcome_registry=outcome_registry,
        _scenario_event_stage=scenario_event_stage,
        _scenario_event_progress=scenario_event_progress,
        _scenario_predicate_random=_scenario_random,
        _environment_stage=environment_stage,
        _current_weather=weather_holder,
        _day_night_stage=day_night_stage,
        # #344 配線漏れ修正: ToolExecutor を experiment runtime 経路で組み立て
        # られるよう、monster_repo と attack_orchestrator を runtime に保持。
        # monster placements の無いシナリオでは両方とも None のまま。
        _monster_repo=monster_repo if scenario.monster_placements else None,
        _attack_orchestrator=monster_attack_orchestrator,
        _world_llm_system_prompt=system_prompt_text,
        _world_llm_system_prompts_by_player_id=system_prompts_by_player_id,
        _include_todo_tools=(
            include_todo_tools
            if include_todo_tools is not None
            else config.tool_mode != _LLM_TOOL_MODE_PURE_SPOT_GRAPH
        ),
        # Prediction (#526 v0): expected_result 露出 policy を config から設定。
        _expected_result_policy=config.expected_result_policy,
        reason_first_two_step_enabled=config.reason_first_two_step_enabled,
        _runtime_config=config,
    )
    travel_stage.set_on_travel_tick_committed(
        runtime._record_committed_player_travel_tick
    )
    world_flag_state.set_change_callback(runtime._record_world_flag_change)
    scenario_event_stage.set_message_callback(
        runtime._append_scenario_event_observation
    )
    if weather_config is None or weather_config.announce_changes:
        environment_stage.set_weather_changed_callback(runtime._append_weather_observation)
    # Phase D-3a: 食料腐敗の観測 bind (stage が存在するときのみ)。
    # #343 対策: per-instance ではなく per-tick 集約 batch callback を bind して、
    # 「野いちご×3 が腐った」のように 1 件にまとめて観測ノイズを抑える。
    # per-instance callback は trace 詳細用にあえて bind しない (集約だけで十分)。
    if food_spoilage_stage is not None:
        food_spoilage_stage.set_spoiled_batch_callback(
            runtime._append_food_spoiled_batch_observation
        )

    # ── PR 2/6 (#227): 任意の DomainEvent を ObservationPipeline 経由で配信する ──
    # PR 2 では PlayerSpokeEvent 用に InMemoryEventPublisher を使い handler を
    # 個別登録していたが、PR 6 で interaction_service など他経路の event も
    # pipeline に流す必要が出たため、event 型ごとの登録ではなく「全 event
    # を pipeline へ流す」publisher に置き換える。chore (#240 後続) で
    # module-level に切り出し。
    # Issue #276: 観測 trace 可視化のため、buffer に積むタイミングで
    # ``TraceEventKind.OBSERVATION`` を記録する。trace_recorder は
    # ``set_trace_recorder`` で後から差し込まれるので provider 経由で参照。
    # PR3 (Encounter Memory): observation を encounter signal に変換する
    # collector を構築し、ObservationAppender の observer slot に注入する。
    # ObservationAppender 側は callable しか知らないので、observation 層と
    # encounter 層を疎結合に保てる (= 後で別 observer を足すのも同じ slot)。
    encounter_collector = EncounterObservationCollector(
        memory=runtime._encounter_memory,
        current_tick_provider=runtime.current_tick,
    )
    observation_appender = ObservationAppender(
        buffer=obs_buffer,
        trace_recorder_provider=lambda: runtime._trace_recorder,
        current_tick_provider=runtime.current_tick,
        observers=[encounter_collector.on_observation],
    )
    pipeline_event_publisher = PipelineEventPublisher(runtime)

    # Phase E-3: プレイヤー個別 outcome の event-driven 配線。
    # registry は既に simulation_service 構築前に作成済み。ここでは broadcast
    # observation 用 callback の bind と PlayerDownedEvent → DEAD ハンドラの
    # subscribe を行う。
    from ai_rpg_world.application.player.handlers.player_downed_outcome_handler import (
        PlayerDownedOutcomeHandler,
    )

    outcome_observation_formatter = PlayerOutcomeObservationFormatter(
        scenario.metadata.player_outcome_messages
    )

    def _broadcast_outcome_change(
        player_id: PlayerId,
        old_outcome: PlayerOutcomeEnum,
        new_outcome: PlayerOutcomeEnum,
    ) -> None:
        """outcome 変化時に全プレイヤーへ観測を流す。

        誰が DEAD / RESCUED / STRANDED になったかは他者の意思決定 (見捨てる
        / 看取る / 弔う) を変えるので、weather と同じ broadcast 扱い。
        所持品観測などより persistent な情報なので schedules_turn=True で
        次の判断機会を強制する。
        """
        actor_name = player_name_map.get(int(player_id), f"プレイヤー({int(player_id)})")
        label = new_outcome.display_label
        message = outcome_observation_formatter.format(
            player_name=actor_name,
            outcome=new_outcome,
        )
        if message is None:
            return  # UNRESOLVED への遷移は通常起きないが防御的に skip
        output = ObservationOutput(
            prose=message,
            structured={
                "type": "player_outcome_resolved",
                "player_id": int(player_id),
                "old_outcome": old_outcome.value,
                "new_outcome": new_outcome.value,
                "label": label,
            },
            observation_category="environment",
            schedules_turn=True,
            breaks_movement=False,
        )
        # 死は世界の設定に従う。追放は常に全員へ。
        #
        # **#914 で `player_downed` の到達範囲は塞いだが、こちらが残っていた。**
        # `grace_ticks: 0` の世界では倒れた次の tick に DEAD が確定するので、
        # 隠したはずの殺害がこの broadcast で全員に漏れる (実 run 007 で
        # 別室の 2 人に「アオイは死亡した」が届いた)。
        #
        # 追放は会議の場で全員が見て決めたことなので、隠す理由が無い。
        # 殺害と追放で扱いを分ける。
        if (
            new_outcome is PlayerOutcomeEnum.DEAD
            and not scenario.death_semantics.announce_globally
        ):
            return
        for pid in runtime.get_player_ids():
            runtime._emit_observation_directly(pid, output)

    def _place_departed_on_death(
        player_id: PlayerId,
        old_outcome: PlayerOutcomeEnum,
        new_outcome: PlayerOutcomeEnum,
    ) -> None:
        """DEAD だけを、倒れた場所から別位置 store へ配置する。"""
        _ = old_outcome
        if new_outcome is not PlayerOutcomeEnum.DEAD:
            return
        body = fallen_body_registry.find(player_id)
        if body is None:
            logger.warning(
                "DEAD outcome has no fallen-body record; departed position "
                "was not initialized: player_id=%s",
                int(player_id),
            )
            return
        departed_position_store.place(player_id, body.spot_id)

    outcome_registry.register_callback(_place_departed_on_death)
    outcome_registry.register_callback(_broadcast_outcome_change)
    # Issue #621: ダウン → DEAD 即時確定をやめ、30 tick の猶予を設ける。
    # grace_timer / grace_stage は simulation_service 構築時 (上の方) で
    # 既に作られているので、ここでは handler だけ pipeline に subscribe する。
    # PlayerDownedEvent → grace_timer.register、PlayerRevivedEvent →
    # grace_timer.cancel、tick stage が grace_ticks 経過後に DEAD 確定。
    from ai_rpg_world.application.player.handlers.player_revived_outcome_handler import (
        PlayerRevivedOutcomeHandler,
    )
    from ai_rpg_world.application.player.handlers.fallen_body_registry_handler import (
        RecordFallenBodyHandler,
        RemoveFallenBodyOnReviveHandler,
    )
    from ai_rpg_world.domain.player.event.status_events import PlayerRevivedEvent
    class _MarkKillerAsHavingSeenTheBody:
        """倒した本人に「その死体を見つけた」を出さないようにする。

        **加害者は現場に残る**ので、死体発見の観測はまず本人へ届く。実 run
        010 では 3 人殺されて発見の観測が 3 回出たが、**3 回とも殺した本人に
        しか届いていない**。文面としても「自分が作った死体を見つけた。
        動かない。」は成立していない。

        新しい state は作らない。Encounter Memory に「もう見た」と刻めば、
        既存の一度きり判定がそのまま働く。**意味の上でも正しい** — 加害者は
        その体を誰よりも先に見ている。

        倒した相手が居ない死け (餓死・事故) では何もしない。
        """

        def handle(self, event: Any) -> None:
            killer = getattr(event, "killer_player_id", None)
            if killer is None:
                return
            victim = getattr(event, "aggregate_id", None)
            if victim is None:
                return
            try:
                encounter_memory.observe(
                    PlayerId(int(killer)),
                    EncounterKey(kind="body", identifier=f"player_{int(victim)}"),
                    int(runtime.current_tick()),
                )
            except Exception:
                logger.warning(
                    "加害者への死体発見抑止に失敗した (killer=%s victim=%s)",
                    killer, victim, exc_info=True,
                )

    # **PlayerDownedOutcomeHandler より先に登録する。** あとに回すと、猶予 0 の
    # 世界で先に DEAD が確定して observation 経路が動き、抑止が間に合わない。
    pipeline_event_publisher.register_handler(
        PlayerDownedEvent, _MarkKillerAsHavingSeenTheBody()
    )
    pipeline_event_publisher.register_handler(
        PlayerDownedEvent,
        RecordFallenBodyHandler(
            registry=fallen_body_registry,
            spot_graph_repository=spot_graph_repo,
            current_tick_provider=lambda: int(runtime.current_tick()),
        ),
    )
    pipeline_event_publisher.register_handler(
        PlayerDownedEvent,
        PlayerDownedOutcomeHandler(
            outcome_registry=outcome_registry,
            grace_timer=death_grace_timer,
            current_tick_provider=lambda: int(runtime.current_tick()),
        ),
    )
    # Issue #621 Phase 5: revive 時の post hoc summary 注入。
    # **PlayerRevivedOutcomeHandler より先に登録する** こと。先に cancel される
    # と grace_timer の downed_at_tick が消えて「N tick の間意識を失っていた」
    # の N が分からなくなる (fail-safe で「数 tick」になるが、正確な値を残す
    # ため順序を守る)。
    from ai_rpg_world.application.player.handlers.player_revived_post_hoc_observation_handler import (
        PlayerRevivedPostHocObservationHandler,
    )
    _caregiver_name_by_pid = {
        int(spawn.player_id): spawn.name for spawn in scenario.player_spawns
    }
    # 倒れている間に自分が対象になった行為の預かり先。倒れている player は
    # observation の宛先から外れる (Phase 4) ので、その瞬間には配れない。
    # 復活時に post hoc summary へ載せる。
    from ai_rpg_world.application.player.services.downed_incident_log import (
        DownedIncidentLog,
    )
    downed_incident_log = DownedIncidentLog()
    pipeline_event_publisher.register_handler(
        PlayerRevivedEvent,
        RemoveFallenBodyOnReviveHandler(fallen_body_registry),
    )
    pipeline_event_publisher.register_handler(
        PlayerRevivedEvent,
        PlayerRevivedPostHocObservationHandler(
            grace_timer=death_grace_timer,
            observation_appender=observation_appender,
            current_tick_provider=lambda: int(runtime.current_tick()),
            caregiver_name_resolver=lambda pid, _d=_caregiver_name_by_pid: (
                _d.get(int(pid))
            ),
            downed_incident_log=downed_incident_log,
        ),
    )
    # 対人行為の対象が倒れていたら、被害を復活まで預かる。
    from ai_rpg_world.application.player.handlers.targeted_while_down_recorder import (
        TargetedWhileDownRecorder,
    )
    from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
        PlayerInteractedWithPlayerEvent,
    )
    pipeline_event_publisher.register_handler(
        PlayerInteractedWithPlayerEvent,
        TargetedWhileDownRecorder(
            incident_log=downed_incident_log,
            player_status_repository=player_status_repo,
            actor_name_resolver=lambda pid, _d=_caregiver_name_by_pid: (
                _d.get(int(pid))
            ),
        ),
    )
    pipeline_event_publisher.register_handler(
        PlayerRevivedEvent,
        PlayerRevivedOutcomeHandler(grace_timer=death_grace_timer),
    )
    # #344 後続: spot_graph_use_item で発火する ConsumableUsedEvent を捌くため、
    # ConsumableEffectHandler を pipeline 経由で subscribe する。これがないと
    # 食料を「使用した」だけで HP / hunger が一切変化しない silent failure
    # になる (第24回実験 OFF で 183 件の use_item が失敗 → 配線後も effect が
    # 発火しないまま、という二重の罠)。
    from ai_rpg_world.application.world.handlers.consumable_effect_handler import (
        ConsumableEffectHandler,
    )
    from ai_rpg_world.domain.item.event.item_event import ConsumableUsedEvent
    consumable_effect_handler = ConsumableEffectHandler(
        item_spec_repository=item_spec_repo,
        player_status_repository=player_status_repo,
        event_publisher=pipeline_event_publisher,
    )
    pipeline_event_publisher.register_handler(
        ConsumableUsedEvent,
        consumable_effect_handler,
    )
    # actor本人のspot到着は、移動commandが確定後に配送する
    # EntityEnteredSpotEventだけを正本として記録する。travel_stage callbackは
    # LLMの再起床だけを担い、同じ到着を二重計上しない。
    from ai_rpg_world.application.encounter.handlers.spot_arrival_encounter_handler import (
        SpotArrivalEncounterHandler,
    )
    from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
        EntityEnteredSpotEvent as _EntityEnteredSpotEvent,
    )

    spot_arrival_encounter_handler = SpotArrivalEncounterHandler(
        memory=encounter_memory,
        current_tick_provider=runtime.current_tick,
        spot_str_id_resolver=lambda spot_int: runtime.id_mapper.get_str(
            "spot", spot_int
        ),
    )
    pipeline_event_publisher.register_handler(
        _EntityEnteredSpotEvent,
        spot_arrival_encounter_handler,
    )
    speech_service = PlayerSpeechApplicationService(
        player_status_repository=player_status_repo,
        event_publisher=pipeline_event_publisher,
        departed_speaker_checker=player_perception_policy.is_departed,
        departed_spot_provider=departed_position_store.find,
    )

    # PR 6 (#227 / Agent C #2): SpotInteractionApplicationService に
    # event_publisher を後付け注入する。これまで None で構築していたため、
    # interaction が graph に積んだ ConnectionStateChangedEvent /
    # SpotObjectStateChangedEvent / SpotObjectInteractedEvent /
    # SpotPublicEffectObservedEvent が pipeline に届かず silent drop されて
    # いた。同じ pipeline publisher を共有する。
    # chore (#240 後続): 旧コードは private field への直接代入だったが、
    # set_event_publisher 経由に正規化。
    interaction_service.set_event_publisher(pipeline_event_publisher)
    # 通常interactionと会議開始は、それぞれ独立したCommandScopeで確定する。
    # CALL_MEETINGを通常interactionの内側へ入れず、専用scopeを順に開始することで
    # 入れ子transactionを避ける。成功eventはどちらもcommit後だけ配送する。
    from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
    from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
        MeetingVoteResolvedEvent,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_interaction_command_repository_provider import (
        InMemoryInteractionCommandRepositoryProviderFactory,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_meeting_command_repository_provider import (
        InMemoryMeetingCommandRepositoryProviderFactory,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_movement_command_repository_provider import (
        InMemoryMovementCommandRepositoryProviderFactory,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_monster_spawn_command_repository_provider import (
        InMemoryMonsterSpawnCommandRepositoryProviderFactory,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_monster_behavior_command_repository_provider import (
        InMemoryMonsterBehaviorCommandRepositoryProviderFactory,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_player_status_tick_command_repository_provider import (
        InMemoryPlayerStatusTickCommandRepositoryProviderFactory,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_reactive_command_repository_provider import (
        InMemoryReactiveCommandRepositoryProviderFactory,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_synchronized_action_command_repository_provider import (
        InMemorySynchronizedActionCommandRepositoryProviderFactory,
    )
    from ai_rpg_world.infrastructure.unit_of_work.interaction_rollback_participants import (
        build_interaction_rollback_participants,
        build_day_night_rollback_participants,
        build_meeting_rollback_participants,
        build_monster_behavior_rollback_participants,
        build_monster_spawn_rollback_participants,
        build_movement_rollback_participants,
        build_reactive_rollback_participants,
        build_scenario_event_rollback_participants,
        build_synchronized_action_rollback_participants,
        build_weather_rollback_participants,
    )
    from ai_rpg_world.infrastructure.unit_of_work.rollback_participant_transaction_adapter import (
        RollbackParticipantTransactionFactory,
    )

    interaction_dispatcher = CommandEventDispatcher()
    interaction_dispatcher.register_after_commit(
        BaseDomainEvent,
        lambda event: pipeline_event_publisher.publish_all((event,)),
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    movement_scope_factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            participants=build_movement_rollback_participants(
                departed_positions=departed_position_store,
                spot_graph=spot_graph_repo,
            ),
        ),
        sync_dispatcher=interaction_dispatcher,
        after_commit_handoff=interaction_dispatcher,
        repository_provider_factory=(
            InMemoryMovementCommandRepositoryProviderFactory(
                spot_graph=spot_graph_repo,
            )
        ),
    )
    movement_service.set_command_scope_factory(movement_scope_factory)

    def _notify_committed_ejection(event: MeetingVoteResolvedEvent) -> None:
        """集計観測の後、会議終了観測の前に追放outcomeを通知する。"""
        if event.ejected_player_id is None:
            return
        outcome_registry.notify_outcome_change(
            event.ejected_player_id,
            PlayerOutcomeEnum.UNRESOLVED,
            PlayerOutcomeEnum.EJECTED,
        )

    interaction_dispatcher.register_after_commit(
        MeetingVoteResolvedEvent,
        _notify_committed_ejection,
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    player_status_tick_scope_factory = CommandScopeFactory(
        InMemoryUnitOfWorkTransactionFactory(data_store),
        sync_dispatcher=interaction_dispatcher,
        after_commit_handoff=interaction_dispatcher,
        repository_provider_factory=(
            InMemoryPlayerStatusTickCommandRepositoryProviderFactory()
        ),
    )
    needs_decay_stage.set_command_scope_factory(player_status_tick_scope_factory)
    status_effects_stage.set_command_scope_factory(player_status_tick_scope_factory)
    scenario_event_scope_factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            participants=build_scenario_event_rollback_participants(
                world_flags=world_flag_state,
                spot_graph=spot_graph_repo,
                progress=scenario_event_progress,
            ),
        ),
        sync_dispatcher=interaction_dispatcher,
        after_commit_handoff=interaction_dispatcher,
        repository_provider_factory=(
            InMemoryInteractionCommandRepositoryProviderFactory(
                spot_graph=spot_graph_repo,
                item_specs=item_spec_repo,
            )
        ),
    )
    scenario_event_stage.set_command_scope_factory(scenario_event_scope_factory)
    reactive_scope_factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            participants=build_reactive_rollback_participants(
                spot_graph=spot_graph_repo,
                condition_evaluator=condition_evaluator,
            ),
        ),
        sync_dispatcher=interaction_dispatcher,
        after_commit_handoff=interaction_dispatcher,
        repository_provider_factory=(
            InMemoryReactiveCommandRepositoryProviderFactory(
                spot_graph=spot_graph_repo,
            )
        ),
    )
    reactive_object_state_stage.set_command_scope_factory(reactive_scope_factory)
    reactive_binding_stage.set_command_scope_factory(reactive_scope_factory)
    synchronized_action_scope_factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            participants=build_synchronized_action_rollback_participants(
                world_flags=world_flag_state,
                spot_graph=spot_graph_repo,
            ),
        ),
        sync_dispatcher=interaction_dispatcher,
        after_commit_handoff=interaction_dispatcher,
        repository_provider_factory=(
            InMemorySynchronizedActionCommandRepositoryProviderFactory(
                spot_graph=spot_graph_repo,
            )
        ),
    )
    sync_resolver_stage.set_command_scope_factory(
        synchronized_action_scope_factory
    )
    weather_scope_factory = CommandScopeFactory[object](
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            participants=build_weather_rollback_participants(
                stage=environment_stage,
            ),
        ),
        sync_dispatcher=interaction_dispatcher,
        after_commit_handoff=interaction_dispatcher,
    )
    environment_stage.set_command_scope_factory(weather_scope_factory)
    if day_night_stage is not None:
        day_night_scope_factory = CommandScopeFactory[object](
            RollbackParticipantTransactionFactory(
                InMemoryUnitOfWorkTransactionFactory(data_store),
                participants=build_day_night_rollback_participants(
                    stage=day_night_stage,
                ),
            ),
            sync_dispatcher=interaction_dispatcher,
            after_commit_handoff=interaction_dispatcher,
        )
        day_night_stage.set_command_scope_factory(day_night_scope_factory)
    if monster_behavior_service is not None:
        monster_behavior_scope_factory = CommandScopeFactory(
            RollbackParticipantTransactionFactory(
                InMemoryUnitOfWorkTransactionFactory(data_store),
                participants=build_monster_behavior_rollback_participants(
                    spot_graph=spot_graph_repo,
                    service=monster_behavior_service,
                ),
            ),
            sync_dispatcher=interaction_dispatcher,
            after_commit_handoff=interaction_dispatcher,
            repository_provider_factory=(
                InMemoryMonsterBehaviorCommandRepositoryProviderFactory(
                    spot_graph=spot_graph_repo,
                )
            ),
        )
        monster_behavior_service.set_command_scope_factory(
            monster_behavior_scope_factory
        )
    if monster_spawn_stage is not None:
        monster_spawn_scope_factory = CommandScopeFactory(
            RollbackParticipantTransactionFactory(
                InMemoryUnitOfWorkTransactionFactory(data_store),
                participants=build_monster_spawn_rollback_participants(
                    spot_graph=spot_graph_repo,
                    stage=monster_spawn_stage,
                ),
            ),
            sync_dispatcher=interaction_dispatcher,
            after_commit_handoff=interaction_dispatcher,
            repository_provider_factory=(
                InMemoryMonsterSpawnCommandRepositoryProviderFactory(
                    spot_graph=spot_graph_repo,
                )
            ),
        )
        monster_spawn_stage.set_command_scope_factory(monster_spawn_scope_factory)
    interaction_participants = build_interaction_rollback_participants(
        world_flags=world_flag_state,
        cooldowns=interaction_cooldown_store,
        departed_positions=departed_position_store,
        spot_graph=spot_graph_repo,
    )
    interaction_scope_factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            participants=interaction_participants,
        ),
        sync_dispatcher=interaction_dispatcher,
        after_commit_handoff=interaction_dispatcher,
        repository_provider_factory=(
            InMemoryInteractionCommandRepositoryProviderFactory(
                spot_graph=spot_graph_repo,
                item_specs=item_spec_repo,
            )
        ),
    )
    interaction_service.set_command_scope_factory(interaction_scope_factory)
    player_interaction_service.set_command_scope_factory(interaction_scope_factory)
    player_interaction_service.set_event_publisher(pipeline_event_publisher)
    meeting_scope_factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            participants=build_meeting_rollback_participants(
                game_phases=game_phase_store,
                spot_graph=spot_graph_repo,
                world_flags=world_flag_state,
                player_outcomes=outcome_registry,
                fallen_bodies=fallen_body_registry,
            ),
        ),
        sync_dispatcher=interaction_dispatcher,
        after_commit_handoff=interaction_dispatcher,
        repository_provider_factory=(
            InMemoryMeetingCommandRepositoryProviderFactory(
                spot_graph=spot_graph_repo,
            )
        ),
    )
    runtime._meeting_command_service = MeetingCommandService(
        meeting_enabled=scenario.meeting_enabled,
        game_phase_store=game_phase_store,
        player_life_query=player_life_query,
        fallen_body_registry=fallen_body_registry,
        player_ids_provider=runtime.get_player_ids,
        current_tick_provider=runtime.current_tick,
        player_name_provider=runtime.get_player_name,
        command_scope_factory=meeting_scope_factory,
        meeting_committed_observer=runtime._record_meeting_started,
        world_flag_state=world_flag_state,
        effect_service=_effect_service,
        ongoing_conditions=(
            MeetingOngoingCondition(
                flag=condition.flag,
                blocks_emergency_button=condition.blocks_emergency_button,
                on_meeting_start=condition.on_meeting_start,
            )
            for condition in scenario.ongoing_conditions
        ),
        condition_resolution_observer=lambda notice: (
            runtime._publish_meeting_condition_resolution(
                notice.flag,
                notice.messages,
            )
        ),
        player_outcome_registry=outcome_registry,
        meeting_ended_observer=runtime._record_meeting_ended,
    )
    # PR4: TIME_OF_DAY_IS / WEATHER_IS condition の評価用 provider 注入。
    # 「夜は釣りできない」「嵐の日は沖の釣り場へ行けない」のような
    # 行動制限条件を interaction precondition から評価できるようにする。
    # day_night_stage / weather_holder が無いシナリオでは provider は None の
    # ままで、該当 condition は「不在として fail」になる (silent skip 回避)。
    if day_night_stage is not None:
        interaction_service.set_time_of_day_phase_provider(
            lambda: day_night_stage.current_time_of_day().phase_name
        )
    _weather_type_provider = lambda: (
        weather_holder["state"].weather_type.value
        if weather_holder.get("state") is not None
        else None
    )
    interaction_service.set_weather_type_provider(_weather_type_provider)
    # PR 3: 対人経路にも同じ provider を配線する。物体経路にだけ入れると
    # 「夜だけ襲える」を宣言した対人 action が常に失敗する (条件は provider
    # 不在で拒否されるため、失敗文の裏に配線漏れが隠れる)。
    if day_night_stage is not None:
        player_interaction_service.set_time_of_day_phase_provider(
            lambda: day_night_stage.current_time_of_day().phase_name
        )
    player_interaction_service.set_weather_type_provider(_weather_type_provider)
    # PR 3: SPOT_LIGHTING_IS の判定に使う実効照明 resolver。現在状態の表示
    # (SpotGraphCurrentStateBuilder) と同じ計算を共有するので、prompt の
    # 「暗い」と前提条件の「暗い」が食い違わない。
    interaction_service.set_effective_lighting_resolver(_effective_lighting_resolver)
    # CALL_MEETING effect を実際の招集につなぐ。宣言していないシナリオでは
    # runtime 側が MEETING_NOT_AVAILABLE で拒否するので、ここは常に差してよい。
    interaction_service.set_meeting_caller(
        lambda player_id, trigger: runtime.call_emergency_meeting(
            player_id,
            trigger=trigger,
        )
    )
    player_interaction_service.set_effective_lighting_resolver(
        _effective_lighting_resolver
    )
    # drop / pickup の witness 配信用。publisher は同じ pipeline を共有し、
    # SpotGraphRecipientStrategy が PlayerDroppedItemEvent / PlayerPickedUpItemEvent
    # を「同スポット・行為者除外」で他プレイヤーに観測として届ける。
    item_transfer_service.set_event_publisher(pipeline_event_publisher)
    merchant_trade_service.set_event_publisher(pipeline_event_publisher)
    player_trade_service.set_event_publisher(pipeline_event_publisher)
    market_service.set_event_publisher(pipeline_event_publisher)
    # 取り落としが誰にも見えないと、採取の結果が手元に無い理由が本人にも
    # 分からない。publisher は runtime を組み終えてからしか作れないので、
    # 市場と同じく後付けする。
    ground_overflow_sink.set_event_publisher(pipeline_event_publisher)
    board_delivery_overflow_sink.set_event_publisher(pipeline_event_publisher)
    # needs decayと状態異常tickは専用CommandScopeが集約eventを収集し、
    # 確定後に同じdispatcherから配送する。旧publisherを差すと二重配送になる。
    # PR-K: monster 攻撃で apply_damage が積む PlayerDownedEvent を流す。
    # これが無いと致命攻撃で outcome=DEAD への遷移も observation broadcast も
    # 起きない silent failure になる (Y 実走で発覚)。
    # monster_attack_orchestrator は monster 不在シナリオで None になり得る
    # ので、None チェックを噛ませる。
    if monster_attack_orchestrator is not None:
        monster_attack_orchestrator.set_event_publisher(pipeline_event_publisher)
    # 昼夜サイクル: フェーズが変わったら TimeOfDayChangedEvent を流す。
    # シナリオが announce_changes=false にしている場合は callback を登録せず
    # silent な phase transition にする。
    # NOTE: day_night_stage が non-None なら day_night_config も必ず non-None
    # (両者を同じブロックで構築している経路) なので、条件式は
    # announce_changes 側だけで足りる。
    if day_night_stage is not None and day_night_config.announce_changes:
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
            TimeOfDayChangedEvent,
        )

        def _on_phase_changed(old_time, new_time) -> None:
            # event publish はゲーム本体の状態遷移とは独立。publisher 側で例外が
            # 起きてもフェーズ遷移自体は完了している (stage._current は更新済)
            # ため、ここで握りつぶしてゲームループを倒さない。ただし error
            # ログを残して埋もれないようにする。
            try:
                graph = spot_graph_repo.find_graph()
                pipeline_event_publisher.publish_all([
                    TimeOfDayChangedEvent.create(
                        aggregate_id=graph.graph_id,
                        aggregate_type="SpotGraphAggregate",
                        old_phase_name=old_time.phase_name,
                        new_phase_name=new_time.phase_name,
                        new_display_text=new_time.display_text,
                        new_is_dark=new_time.is_dark,
                    )
                ])
            except Exception:
                _logger = logging.getLogger(__name__)
                _logger.error(
                    "failed to publish TimeOfDayChangedEvent (phase %s -> %s)",
                    old_time.phase_name, new_time.phase_name,
                    exc_info=True,
                )

        day_night_stage.set_phase_changed_callback(_on_phase_changed)

    runtime._speech_service = speech_service
    runtime._speech_event_publisher = pipeline_event_publisher
    # 蘇生猶予タイマーを runtime から読めるようにする。「PlayerDownedEvent が
    # handler まで届いたか」を外から確かめる唯一の手掛かりで、publish された
    # ことと handler が走ったことは別物 (registry 登録漏れで静かに落ちる)。
    runtime._death_grace_timer = death_grace_timer
    # 「倒れている間にされたこと」の預かり先。何が記録された / されなかったか
    # を外から確かめられないと、致死の一撃が誤って混ざる類の破綻を固定できない。
    runtime._downed_incident_log = downed_incident_log
    runtime._observation_appender = observation_appender

    # Issue #283 後続: episodic memory pipeline の on/off。
    # episodic ON のときだけ scenario load 時に matcher + chunk coordinator +
    # passive recall を組み立てる。OFF なら従来動作。
    # PR #330: シナリオ非依存の builder に統一。world_episodic_wiring 経由の
    # 旧 alias も後方互換で生きているが、application 層から直接 import する。
    # #558 MEDIUM-1 後続: 親 gate を env 直読み (is_episodic_enabled) から
    # config.episodic_enabled に寄せ、ResolvedLlmRuntimeConfig 単一窓口に揃えた。
    # config=None のときは from_mapping() が空 mapping を解決する (= env は読まず
    # 全 default = episodic OFF)。実験経路 (run_scenario_experiment.py) は profile
    # から明示 config を組んで渡すため env に依存しない。explicit config が effect
    # するので「同 env を 2 経路で別解釈する」silent failure を構造で防げる。
    from ai_rpg_world.application.llm.wiring.episodic_stack import (
        build_episodic_stack,
    )
    # 敵対的レビュー HIGH 1: 「episodic を前提にする機能群」の fail-fast を親 gate の
    # 外に出す。P-U1 (GOAL_STAGNATION_EVIDENCE) / P-U2 (STAGNATION_PRESSURE) / 案A
    # (STAGNATION_REASONING) はいずれも episodic pipeline (固着パス / 停滞感 store /
    # 熟考ラッチ) の内側でしか配線されない。従来これらの相互ガードは
    # `if config.episodic_enabled:` の内側にあったため、LLM_EPISODIC_ENABLED を
    # 立て忘れたまま各 flag を ON にすると、ブロックごと skip されて fail-fast すら
    # 走らず「flag は立てたのに機能が一生動かず警告も出ない」静かな失敗になっていた
    # (本 PR 群が売りにする「起動時 fail-fast」に正面から反する)。episodic 前提の
    # flag が 1 つでも ON なら、親 gate に入る前にここで LLM_EPISODIC_ENABLED を要求
    # して落とす。
    if not config.episodic_enabled:
        _episodic_dependent_flags = {
            "GOAL_STAGNATION_EVIDENCE_ENABLED": (
                config.goal_stagnation_evidence_enabled
            ),
            "STAGNATION_PRESSURE_ENABLED": config.stagnation_pressure_enabled,
            "STAGNATION_REASONING_ENABLED": config.stagnation_reasoning_enabled,
        }
        _on_but_orphaned = [
            name for name, enabled in _episodic_dependent_flags.items() if enabled
        ]
        if _on_but_orphaned:
            raise ValueError(
                f"{', '.join(_on_but_orphaned)}=1 だが LLM_EPISODIC_ENABLED が OFF の"
                "ため episodic pipeline (固着パス / 停滞感 store / 熟考ラッチ) が丸ごと"
                "構築されず、これらの機能が一生動かない (静かな失敗)。"
                "LLM_EPISODIC_ENABLED=1 も設定してください。"
            )
    # prompt dataset は記憶機能ではないが、各行へ安定した being_id を保存する。
    # episodic の親 gate に入れると lean profile では最初の LLM 呼び出しまで
    # resolver が未配線になり、記録だけが失敗する。capture 自身の要件として
    # 補助 Being を起動時に構築し、全参加者を fail-fast で provision する。
    if config.prompt_dataset_capture_enabled:
        runtime._wire_auxiliary_tool_stack()
        for s in getattr(scenario, "player_spawns", ()):
            runtime._aux_being_provisioning.ensure_attached(
                PlayerId(int(s.player_id))
            )
    if config.episodic_enabled:
        # Phase 3 Step 3e-3: ChunkCoordinator / Scheduler / passive_recall は
        # episode_store 経路で being_id 必須化済。world_runtime の aux Being 配線
        # を早期に確立し、各 player_spawn 分の Being を provision しておく。
        if not config.prompt_dataset_capture_enabled:
            runtime._wire_auxiliary_tool_stack()
            for s in getattr(scenario, "player_spawns", ()):
                try:
                    runtime._aux_being_provisioning.ensure_attached(
                        PlayerId(int(s.player_id))
                    )
                except Exception:
                    logger.exception(
                        "world_runtime: Being provision failed for player_id=%s (chunk "
                        "coordinator は silent skip するが、episode が書かれない)",
                        s.player_id,
                    )

        # Issue #295 後続: LLM 主観文付与の opt-in 配線。
        # LLM_EPISODIC_SUBJECTIVE_ENABLED (default on, #308) かつ LiteLLMClient
        # が取れるときだけ chunk write 後に裏で LLM が走り、interpreted /
        # recall_text を上書きする。失敗時は #305 でテンプレ既定値が draft に
        # 入っているのでそのまま流れる。
        # PR #309: 同期で LLM を待つとゲーム tick が止まる (1〜3 秒)。
        # ThreadPoolEpisodicSubjectiveScheduler で裏に逃がし、完了時に
        # episode_store を同じ episode_id で上書きする (Pattern A:
        # Fire-and-forget + eventual consistency)。
        subjective_scheduler = None
        persona_provider: Optional[Callable[[PlayerId], str]] = None
        shared_episode_store = None  # scheduler が wire されたときだけ事前生成
        # U2 (証拠台帳統一設計 / default OFF): BELIEF_EVIDENCE_ENABLED のときだけ
        # evidence buffer + transcriber を構築する。「配線 (wire) と有効化
        # (enable) の分離」規約に従い、OFF なら None のまま扱う (= 転記コード
        # パス自体は通るが不活性)。
        from ai_rpg_world.application.llm.wiring.feature_flags import (
            log_belief_attribution_enabled_state,
            log_belief_consolidation_enabled_state,
            log_belief_evidence_enabled_state,
            log_error_driven_reinterpretation_enabled_state,
            log_error_gated_encoding_enabled_state,
            log_hearsay_enabled_state,
            log_memo_distill_enabled_state,
            log_pending_prediction_enabled_state,
            log_recall_hit_boost_enabled_state,
            log_salience_structured_failure_enabled_state,
            log_state_collapse_evidence_enabled_state,
            log_unconscious_context_enabled_state,
        )

        _belief_evidence_enabled = config.belief_evidence_enabled
        log_belief_evidence_enabled_state(_belief_evidence_enabled)
        # U9a (予測誤差統一設計 部品5・誤差駆動再解釈 / default OFF): 実効的には
        # reinterpretation_enabled (段1) と PREDICTION_CONTEXT_ID_ENABLED (U1) の
        # 両方が ON でないと stamp 対象の recall observation が無く安全に縮退する。
        _error_driven_reinterpretation_enabled = (
            config.error_driven_reinterpretation_enabled
        )
        log_error_driven_reinterpretation_enabled_state(
            _error_driven_reinterpretation_enabled
        )
        # U9b (予測誤差統一設計 部品5・想起の信用割り当て / default OFF): U9a と
        # 対称に、的中側 (思い出したから当たった) を recall ranking boost に
        # 還流する。実効的には reinterpretation_enabled (段1) と
        # PREDICTION_CONTEXT_ID_ENABLED (U1) の両方が ON でないと record_hit
        # 対象の recall observation が無く安全に縮退する。
        # 強さ (strength=1) と cap (RECALL_HIT_BOOST_DEFAULT_CAP) は小さく
        # 始める前提の定数 (habituation_strength と同じく env 非公開。
        # 「当たる記憶」の固定化を防ぐための上限)。
        _recall_hit_boost_enabled = config.recall_hit_boost_enabled
        log_recall_hit_boost_enabled_state(_recall_hit_boost_enabled)
        _recall_hit_boost_strength = 1
        # U4 (予測誤差統一設計 部品3 / default OFF): attribution + CONFIRMATION。
        # 実効的には U1 (PREDICTION_CONTEXT_ID_ENABLED) が ON でないと belief_ids
        # が流れてこないが、ここでは独立に flag を解決するだけに留める
        # (U1 flag OFF のまま本 flag だけ ON でも in_context_belief_ids は常に
        # 空になり安全に縮退する)。
        _belief_attribution_enabled = config.belief_attribution_enabled
        log_belief_attribution_enabled_state(_belief_attribution_enabled)
        # P4 (reflect): 固着パスに目的への前進評価を足すか。
        from ai_rpg_world.application.llm.wiring.feature_flags import (
            log_goal_reflect_enabled_state,
            log_goal_stagnation_evidence_enabled_state,
            log_stagnation_pressure_enabled_state,
            log_stagnation_reasoning_enabled_state,
        )

        _goal_reflect_enabled = config.goal_reflect_enabled
        log_goal_reflect_enabled_state(_goal_reflect_enabled)
        # P-U1 (目的停滞の evidence 化): reflect の stalled/misaligned verdict を
        # goal: 軸の evidence に変換するか。
        _goal_stagnation_evidence_enabled = config.goal_stagnation_evidence_enabled
        log_goal_stagnation_evidence_enabled_state(_goal_stagnation_evidence_enabled)
        # P-U2 (停滞感 store): reflect verdict を停滞感カウンタに畳み込むか。
        _stagnation_pressure_enabled = config.stagnation_pressure_enabled
        log_stagnation_pressure_enabled_state(_stagnation_pressure_enabled)
        # 案A (band-gated thinking): 停滞 strong の局面で reflect 注入直後の 1 行動に
        # reasoning を焚くか。
        _stagnation_reasoning_enabled = config.stagnation_reasoning_enabled
        log_stagnation_reasoning_enabled_state(_stagnation_reasoning_enabled)
        # U3b: 固着パス。BELIEF_EVIDENCE_ENABLED (PREDICTION_ERROR 転記) とは
        # 独立した flag だが、両方とも同じ evidence buffer を読み書きするので
        # どちらか一方でも ON なら buffer store 自体は作る。
        _belief_consolidation_enabled = config.belief_consolidation_enabled
        log_belief_consolidation_enabled_state(_belief_consolidation_enabled)
        # 敵対的レビュー HIGH-1 fail-fast: P-U1 (goal_stagnation_evidence) /
        # P-U2 (stagnation_pressure) はどちらも BeliefConsolidationCoordinator
        # (固着パス) 経由でしか動かないが、その coordinator 自体は
        # belief_consolidation_enabled が ON のときしか構築されない
        # (episodic_stack.py の `if belief_consolidation_enabled and
        # belief_evidence_buffer_store is not None` 分岐)。coordinator
        # コンストラクタ内の fail-fast (goal_reflect_enabled 必須等) は
        # coordinator が実際に構築されたときにしか働かないため、それより前の
        # ここで相互ガードしないと「flag を ON にしたのに coordinator が
        # 一度も作られず、カウンタも evidence 化も一生 0 のまま、警告すら出ない」
        # 静かな失敗になる (本 PR 群が売りにする「起動時 fail-fast で弾く」に
        # 正面から反する)。
        if _goal_stagnation_evidence_enabled and not _belief_consolidation_enabled:
            raise ValueError(
                "GOAL_STAGNATION_EVIDENCE_ENABLED=1 だが BELIEF_CONSOLIDATION_ENABLED "
                "が OFF のため固着パス (BeliefConsolidationCoordinator) が構築されず、"
                "reflect の stalled/misaligned verdict を evidence 化する経路が丸ごと"
                "動かない (静かな失敗)。BELIEF_CONSOLIDATION_ENABLED=1 も設定してください。"
            )
        if _stagnation_pressure_enabled and not _belief_consolidation_enabled:
            raise ValueError(
                "STAGNATION_PRESSURE_ENABLED=1 だが BELIEF_CONSOLIDATION_ENABLED が "
                "OFF のため固着パス (BeliefConsolidationCoordinator) が構築されず、"
                "reflect verdict を停滞感カウンタに畳み込む経路が丸ごと動かない "
                "(静かな失敗)。BELIEF_CONSOLIDATION_ENABLED=1 も設定してください。"
            )
        # 案A fail-fast: band-gated thinking は band (STAGNATION_PRESSURE) と
        # reflect 注入 (= ラッチ武装, GOAL_REFLECT) の両方に依存する。どちらか
        # 欠けると「flag を ON にしたのに熟考が一生焚かれず警告も出ない」静かな
        # 失敗になるため起動時に弾く。
        if _stagnation_reasoning_enabled and not _stagnation_pressure_enabled:
            raise ValueError(
                "STAGNATION_REASONING_ENABLED=1 だが STAGNATION_PRESSURE_ENABLED が "
                "OFF のため band (strong 判定) が供給されず、熟考ゲートが一生発火"
                "しない (静かな失敗)。STAGNATION_PRESSURE_ENABLED=1 も設定してください。"
            )
        if _stagnation_reasoning_enabled and not _goal_reflect_enabled:
            raise ValueError(
                "STAGNATION_REASONING_ENABLED=1 だが GOAL_REFLECT_ENABLED が OFF の"
                "ため reflect 注入 (= 熟考ラッチの武装トリガ) が起きず、熟考ゲートが"
                "一生発火しない (静かな失敗)。GOAL_REFLECT_ENABLED=1 も設定してください。"
            )
        # U6: salience 判定 + STRUCTURED_FAILURE 転記 (default OFF)。他 2 flag
        # 同様、同じ evidence buffer を共有するので ON なら buffer store を作る
        # 条件に加える。
        _salience_structured_failure_enabled = (
            config.salience_structured_failure_enabled
        )
        log_salience_structured_failure_enabled_state(
            _salience_structured_failure_enabled
        )
        # PR-D (状態破綻を高 salience evidence として記憶化 / default OFF):
        # is_down への遷移と hunger max 到達を STATE_COLLAPSE 転記する。他の
        # salience 系 flag と同じ evidence buffer を共有するので、ON なら
        # buffer store を作る条件に加える。判定は既存の状態遷移そのものであり
        # LLM 呼び出しは追加しない (structured_failure と同じ「転記のみ」方針)。
        _state_collapse_evidence_enabled = config.state_collapse_evidence_enabled
        log_state_collapse_evidence_enabled_state(_state_collapse_evidence_enabled)
        # U8 (予測誤差統一設計 部品2・誤差ゲート付き符号化 / default OFF):
        # 境界 (2a, chunk_coordinator へ伝播) + 解像度 (2b, 下の subjective
        # service 構築時に salience_enabled と合わせて評価) を一括ゲートする。
        # evidence buffer とは無関係な独立 flag なので buffer store 条件には
        # 加えない。
        _error_gated_encoding_enabled = config.error_gated_encoding_enabled
        log_error_gated_encoding_enabled_state(_error_gated_encoding_enabled)
        # U5: MEMO_DISTILL 転記 (default ON)。memo を手帳で終わらせず
        # semantic evidence へ蒸留するため、明示 OFF でだけ止める。
        # 他 3 flag 同様、同じ evidence
        # buffer を共有するので ON なら buffer store を作る条件に加える。
        _memo_distill_enabled = config.memo_distill_enabled
        log_memo_distill_enabled_state(_memo_distill_enabled)
        # U7 (予測誤差統一設計 / 無意識コンテキスト / default OFF): belief top-K +
        # L5 を chunk 主観補完 LLM に渡すか。他 flag と独立 (evidence buffer は
        # 使わない = 読み取り専用の追加コンテキストなので buffer store 条件には
        # 加えない)。
        _unconscious_context_enabled = config.unconscious_context_enabled
        log_unconscious_context_enabled_state(_unconscious_context_enabled)
        # U10a (予測誤差統一設計 部品6・pending prediction / default OFF):
        # 抽出・保持・再浮上を一括ゲートする。evidence buffer とは無関係な
        # 独立 flag (別の per-Being store を使う) なので buffer store 条件には
        # 加えない。
        _pending_prediction_enabled = config.pending_prediction_enabled
        log_pending_prediction_enabled_state(_pending_prediction_enabled)
        _hearsay_requested = config.hearsay_enabled
        # H-1 (伝聞の入力衛生 / 横断レビュー): HEARSAY は BELIEF_EVIDENCE_ENABLED
        # (evidence buffer + transcriber) が前提。抽出側 (chunk 補完 LLM の
        # heard_claims 節) だけ ON で転記側の transcriber が無いと、抽出コスト
        # (prompt 節 + LLM 出力) を払うだけで転記点
        # (_record_belief_evidence_if_applicable) が transcriber None のため
        # 黙って捨てる「誘うのに黙って捨てる」静かな失敗になる (MEMO_DISTILL
        # 事件の構造再演)。GOAL_REVISION×GOAL_STORE (直下) と同じパターンで、
        # BELIEF_EVIDENCE が OFF なら HEARSAY も実効 OFF に畳み、抽出コストも
        # 払わないようにする。
        if _hearsay_requested and not _belief_evidence_enabled:
            logger.warning(
                "HEARSAY_ENABLED=1 だが BELIEF_EVIDENCE_ENABLED が OFF のため "
                "伝聞の抽出・転記は無効化される (belief evidence transcriber が "
                "前提)。BELIEF_EVIDENCE_ENABLED=1 も設定してください。"
            )
        _hearsay_enabled = _hearsay_requested and _belief_evidence_enabled
        log_hearsay_enabled_state(_hearsay_enabled)
        # GOAL_REVISION_ENABLED と同様、畳み込んだ実効値を runtime にも保持する
        # (テストや後続処理が「実際に何が有効か」を config ミスに関わらず
        # 一箇所から読めるようにする)。
        runtime._hearsay_enabled = _hearsay_enabled
        # P5 (目的層 G1): GOAL_STORE_ENABLED ON のとき goal store を構築し
        # runtime に保持する。【現在の目的】provider (prompt builder 側) と実験
        # snapshot stub がここから拾う。OFF なら None のまま (静的シナリオ文字列)。
        from ai_rpg_world.application.llm.wiring.feature_flags import (
            log_goal_store_enabled_state,
        )

        _goal_store_enabled = config.goal_store_enabled
        log_goal_store_enabled_state(_goal_store_enabled)
        if _goal_store_enabled:
            from ai_rpg_world.application.llm.services.in_memory_goal_journal_store import (
                InMemoryGoalJournalStore,
            )

            runtime._goal_journal_store = InMemoryGoalJournalStore()
        # P6 (目的の見直し / G2): GOAL_REVISION_ENABLED ON かつ goal store が
        # あるとき、goal_update を反映する applier を構築する。goal store が
        # 無ければ改訂しようがないので何もしない (revision は store が前提)。
        from ai_rpg_world.application.llm.wiring.feature_flags import (
            log_goal_revision_enabled_state,
        )

        _goal_revision_requested = config.goal_revision_enabled
        # revision は goal store が前提。GOAL_REVISION_ENABLED だけ ON で
        # GOAL_STORE_ENABLED が OFF だと、goal_update を schema に露出しつつ
        # applier が無く「誘うのに黙って捨てる」= 静かな失敗 (本 PR が撤回した
        # まさにその挙動を config ミスで再現) になる。両者を畳んで、store が
        # 無ければ revision も実効 OFF にし、schema 露出も起きないようにする。
        if _goal_revision_requested and runtime._goal_journal_store is None:
            logger.warning(
                "GOAL_REVISION_ENABLED=1 だが GOAL_STORE_ENABLED が OFF のため "
                "目的の改訂は無効化される (goal store が前提)。GOAL_STORE_ENABLED=1 "
                "も設定してください。"
            )
        runtime._goal_revision_enabled = (
            _goal_revision_requested and runtime._goal_journal_store is not None
        )
        log_goal_revision_enabled_state(runtime._goal_revision_enabled)
        # P8: 目的の清算 (goal_outcome) が起きたとき belief evidence へ転記する
        # transcriber は、この下で BELIEF 系 flag 依存で後から構築される。U7 と
        # 同じ遅延 holder で applier に渡し、transcriber 確定後に中身を埋める
        # (belief 経路が OFF のときは None のまま = 転記なしで清算だけ行う)。
        _goal_settlement_transcriber_holder: list[Any] = [None]
        if runtime._goal_revision_enabled:
            from ai_rpg_world.application.llm.services.goal_revision_applier import (
                GoalRevisionApplier,
            )

            runtime._goal_revision_applier = GoalRevisionApplier(
                runtime._goal_journal_store,
                observation_sink=runtime._emit_goal_observation,
                current_tick_provider=runtime.current_tick,
                now_provider=lambda: datetime.now(timezone.utc),
                settlement_transcriber_provider=(
                    lambda: _goal_settlement_transcriber_holder[0]
                ),
                trace_recorder_provider=lambda: runtime._trace_recorder,
            )
        # U7: subjective service の構築 (この少し下) は semantic スタック構築
        # (build_episodic_stack 呼び出し、この関数のずっと下) より先に走るため、
        # belief 取得に使う SemanticPassiveRecallService をこの時点ではまだ
        # 作れない (semantic_memory_store が未確定)。provider は「呼ばれた瞬間に
        # このリストの中身を見る」遅延解決にし、build_episodic_stack が返した
        # semantic_memory_store で後から埋める (下の「U7: 無意識コンテキスト用
        # semantic recall service を確定させる」ブロックを参照)。
        _unconscious_context_semantic_recall_holder: list[Any] = [None]
        belief_evidence_buffer_store = None
        belief_evidence_transcriber = None
        if (
            _belief_evidence_enabled
            or _belief_consolidation_enabled
            or _salience_structured_failure_enabled
            or _memo_distill_enabled
            or _state_collapse_evidence_enabled
        ):
            from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
                InMemoryBeliefEvidenceBufferStore,
            )

            belief_evidence_buffer_store = InMemoryBeliefEvidenceBufferStore()
            if _belief_evidence_enabled:
                from ai_rpg_world.application.llm.services.belief_evidence_transcriber import (
                    BeliefEvidenceTranscriber,
                )

                # P3 (CONFIRMATION 関連性ゲート): belief_id → (tags, text) を
                # semantic store から遅延ルックアップする provider。CONFIRMATION
                # 転記時 (run 中) には episodic_stack / semantic store が確定して
                # いるので、参照を lambda で遅延評価する。store 未構築 / belief
                # 不在なら None を返し、ゲートは安全側 (積まない) に倒れる。
                # 注: in_context_belief_ids に流れる id は passive recall 時点の
                # entry_id (prompt_builder が c.entry.entry_id で採る) であり、
                # lineage の belief_id ではない。revise 済み belief は
                # entry_id != belief_id になる (新 entry が別 entry_id を持ち
                # belief_id だけ継ぐ) ため、必ず entry_id で照合する
                # (belief_id で照合すると revise 済み belief が永久に一致しなくなる)。
                def _belief_axis_lookup(being_id, recalled_entry_id):
                    stack = runtime._episodic_stack
                    store = getattr(stack, "semantic_memory_store", None) if stack else None
                    if store is None:
                        return None
                    try:
                        entries = store.list_for_being(being_id)
                    except Exception:
                        logger.warning(
                            "belief_axis_lookup: semantic_store.list_for_being "
                            "failed; CONFIRMATION ゲートは安全側 (None) に倒れる",
                            exc_info=True,
                        )
                        return None
                    for entry in entries:
                        if entry.entry_id == recalled_entry_id:
                            return (tuple(entry.tags), entry.text)
                    return None

                belief_evidence_transcriber = BeliefEvidenceTranscriber(
                    belief_evidence_buffer_store,
                    trace_recorder_provider=lambda: runtime._trace_recorder,
                    current_tick_provider=runtime.current_tick,
                    belief_axis_provider=_belief_axis_lookup,
                )
                # P8: goal 清算の転記も同じ transcriber が担う。上で先に構築した
                # GoalRevisionApplier の遅延 holder をここで埋める。
                _goal_settlement_transcriber_holder[0] = belief_evidence_transcriber
        # P-U2 (停滞感 store): ON のときだけ in-memory store を構築し、
        # BeliefConsolidationCoordinator に注入する。runtime に保持するのは
        # snapshot stub (_wiring_stub_from_world_runtime) から拾えるように
        # するため (checklist #27。goal_journal_store と同じ扱い)。
        runtime._stagnation_pressure_store = None
        if _stagnation_pressure_enabled:
            from ai_rpg_world.application.llm.services.in_memory_stagnation_pressure_store import (
                InMemoryStagnationPressureStore,
            )

            runtime._stagnation_pressure_store = InMemoryStagnationPressureStore()
        # 案A (band-gated thinking): ON のときだけラッチを構築する。
        # ``_emit_reflect_observation`` が停滞注入時に arm し、run_phase_a が
        # 次行動で consume する。transient なので snapshot には載せない。
        runtime._stagnation_reasoning_latch = None
        if _stagnation_reasoning_enabled:
            from ai_rpg_world.application.llm.services.in_memory_stagnation_reasoning_latch import (
                InMemoryStagnationReasoningLatch,
            )

            runtime._stagnation_reasoning_latch = InMemoryStagnationReasoningLatch()
        if config.episodic_subjective_enabled:
            from ai_rpg_world.application.llm.services.episodic_chunk_subjective_fields import (
                EpisodicChunkSubjectiveFieldsService,
            )
            from ai_rpg_world.application.llm.services.episodic_subjective_completion_schedulers import (
                ThreadPoolEpisodicSubjectiveScheduler,
            )
            from ai_rpg_world.application.llm.wiring._llm_client_factory import (
                create_llm_client_from_config,
            )
            from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient

            try:
                _client = create_llm_client_from_config(config)
            except Exception:
                logger.exception("LLM client factory failed; subjective service disabled")
                _client = None
            if isinstance(_client, LiteLLMClient):
                # subjective service は scheduler 内部に閉じ込める。
                # episode_store は build_episodic_stack 内で作るが、
                # scheduler に渡す必要があるので先に作ってから stack 構築側に
                # 渡したい — が wiring の都合で一旦同じ store を共有する経路
                # にしておく (= scheduler は episode_store への参照を持ち、
                # stack 側も同じ store を使う)。
                # 簡潔さ優先で「stack を組んでから scheduler を作って差し戻す」
                # 二段階構築は避け、ここで store を先に作って両方に渡す。
                from ai_rpg_world.application.llm.services.in_memory_subjective_episode_store import (
                    InMemorySubjectiveEpisodeStore,
                )

                shared_episode_store = InMemorySubjectiveEpisodeStore()
                # U7: provider 自体は _unconscious_context_enabled が False でも
                # 常に None のまま渡して構わない (service 側で「配線と有効化の
                # 分離」を担保済み)。ON のときだけ実体を組む。belief を読む
                # SemanticPassiveRecallService はこの時点でまだ確定していない
                # (semantic_memory_store は build_episodic_stack がこの後で
                # 構築する) ため、holder 経由の遅延解決にする。L5 (self_image /
                # world_view) は RollingSummary 使用時のみ短期記憶が
                # get_long_summary_text を実装するので、無ければ渡さない
                # (= 従来通り省略される)。
                _unconscious_context_provider = None
                if _unconscious_context_enabled:
                    from ai_rpg_world.application.llm.wiring.unconscious_context_provider import (
                        build_unconscious_context_provider,
                    )

                    _get_long_summary_text = getattr(
                        short_term_memory, "get_long_summary_text", None
                    )
                    _long_summary_text_provider = (
                        (
                            lambda pid, _f=_get_long_summary_text: _f(
                                PlayerId(pid)
                            )
                        )
                        if callable(_get_long_summary_text)
                        else None
                    )
                    _unconscious_context_provider = build_unconscious_context_provider(
                        semantic_recall_service_provider=(
                            lambda: _unconscious_context_semantic_recall_holder[0]
                        ),
                        resolve_being=lambda pid: (
                            runtime._aux_being_resolver.resolve_being_id(
                                runtime._aux_being_default_world_id, pid
                            )
                            if runtime._aux_being_resolver is not None
                            and runtime._aux_being_default_world_id is not None
                            else None
                        ),
                        long_summary_text_provider=_long_summary_text_provider,
                    )
                # U6: flag OFF なら salience_enabled=False (= system prompt が
                # 導入前と byte 同一)。
                # U8 (部品2b): error_gated_encoding_enabled は
                # salience_enabled が False のときは無効化される (連動先の
                # salience が存在しないため。_build_system_prompt 側で保証)。
                _subjective_service = EpisodicChunkSubjectiveFieldsService(
                    _client,
                    salience_enabled=_salience_structured_failure_enabled,
                    unconscious_context_provider=_unconscious_context_provider,
                    unconscious_context_enabled=_unconscious_context_enabled,
                    error_gated_encoding_enabled=_error_gated_encoding_enabled,
                    pending_prediction_enabled=_pending_prediction_enabled,
                    hearsay_enabled=_hearsay_enabled,
                )
                # scheduler と chunk_coordinator (= stack) が同じ store を
                # 共有することで、worker が書き込んだ merged episode を
                # passive_recall が読める ( = Pattern A の整合性条件)。
                # Phase 3 Step 3e-3: scheduler は episode_store を being_id 経路で
                # 触る。being_id は chunk_coordinator から submit 引数で渡される。
                subjective_scheduler = ThreadPoolEpisodicSubjectiveScheduler(
                    _subjective_service,
                    shared_episode_store,
                    max_workers=1,
                    max_queue_size=100,
                    trace_recorder_provider=lambda: runtime._trace_recorder,
                    current_tick_provider=runtime.current_tick,
                    # U2: 非同期経路 (worker thread) の完了点。flag OFF なら
                    # None のまま (= 従来動作と完全互換)。
                    belief_evidence_transcriber=belief_evidence_transcriber,
                    # U4: default False。attribution + CONFIRMATION の計算自体を
                    # 行うかどうか (transcriber が None なら本来無関係だが、
                    # 明示的に flag を伝播しておく)。
                    belief_attribution_enabled=_belief_attribution_enabled,
                    # U9a: default False。recall_buffer_store 自体は
                    # build_episodic_stack がこの後で構築するため、この時点では
                    # 未確定 (= None のまま)。build_episodic_stack 完了後に
                    # set_recall_buffer_store で差し込む (下の「U9a: recall_buffer
                    # を scheduler に後から差し込む」ブロックを参照)。
                    error_driven_reinterpretation_enabled=(
                        _error_driven_reinterpretation_enabled
                    ),
                    # U9b: default False。recall_success_store 自体は
                    # build_episodic_stack がこの後で構築するため、この時点では
                    # 未確定 (= None のまま)。build_episodic_stack 完了後に
                    # set_recall_success_store で差し込む (下の「U9b:
                    # recall_success_store を scheduler に後から差し込む」
                    # ブロックを参照)。
                    recall_hit_boost_enabled=_recall_hit_boost_enabled,
                    # U10a: default False。pending_prediction_store 自体は
                    # build_episodic_stack がこの後で構築するため、この時点
                    # では未確定 (= None のまま)。build_episodic_stack 完了後に
                    # set_pending_prediction_store で差し込む。
                    pending_prediction_enabled=_pending_prediction_enabled,
                )
                # 各 player の persona_block を player_id 引きで返す provider。
                # world_character (= 操作対象) は rich persona、その他は spawn 名
                # 由来の fallback persona になっている system_prompts_by_player_id
                # と同じ規則で組み立てる。
                _persona_by_pid: Dict[int, str] = {}
                if len(scenario.player_spawns) > 1 and world_character is not None:
                    ec_cid = (world_character.character_id or "").strip()
                    ec_name = (world_character.name or "").strip()
                    for s in scenario.player_spawns:
                        if (ec_cid and s.string_id == ec_cid) or (ec_name and s.name == ec_name):
                            _persona_by_pid[int(s.player_id)] = persona_block
                        else:
                            _persona_by_pid[int(s.player_id)] = (
                                build_persona_block_from_character(
                                    None, fallback_display_name=s.name
                                )
                            )
                elif scenario.player_spawns:
                    # 単独 spawn (旧来構成) や world_character 未指定: 全 player に
                    # 既存の persona_block を流用 (fallback 含む)
                    for s in scenario.player_spawns:
                        _persona_by_pid[int(s.player_id)] = persona_block
                persona_provider = lambda pid, _d=_persona_by_pid: _d.get(int(pid.value), "")
            else:
                logger.info(
                    "LLM_EPISODIC_SUBJECTIVE_ENABLED=1 だが LiteLLMClient 未使用 "
                    "(LLM_CLIENT=litellm が必要)。subjective scheduler を無効化。"
                )
        # #526 後続: semantic 拡張のフラグ解決。world_runtime でも
        # SEMANTIC_PASSIVE_TOP_K / SEMANTIC_LLM_GIST_ENABLED で「学びを作る
        # (promotion) / 出す (passive recall)」を on/off できるようにする。
        # 既定 OFF (top_k=0 / gist off) で従来の episodic-only 動作を保つ。
        # フラグは env を直読みせず ResolvedLlmRuntimeConfig (= config) から取る。
        # こうしないと create_world_runtime(config=...) の明示 config が
        # semantic だけ無視され、短期記憶など他設定との config 契約が崩れる。
        _semantic_top_k = config.semantic_passive_top_k
        _semantic_gist_enabled = config.semantic_llm_gist_enabled
        # U3b: 固着パスは belief journal (semantic_memory_store) への書き込みを
        # 前提とするため、他の semantic 系フラグが OFF でも semantic スタック
        # 自体は組む必要がある。U7 (無意識コンテキスト) も同じ理由で強制する:
        # belief top-K を読むには semantic_memory_store が要るため、
        # SEMANTIC_PASSIVE_TOP_K=0 のまま UNCONSCIOUS_CONTEXT_ENABLED だけ ON
        # にしても semantic スタックが組まれないと belief が一切取れない。
        # 能動記憶ツール (memory_search_semantic / memory_explore_related) も
        # semantic_memory_store / memory_link_store を前提とするため、露出フラグ
        # が ON のときは同じスタックを組む。tool 定義の露出自体は
        # get_tool_definitions() が config と executor の AND で決める。
        _semantic_enabled = (
            _semantic_top_k > 0
            or _semantic_gist_enabled
            or _belief_consolidation_enabled
            or _unconscious_context_enabled
            or config.semantic_search_enabled
            or config.episodic_explore_related_enabled
        )
        _semantic_gist_service = None
        _semantic_persona_resolver = None
        if _semantic_enabled:
            _names_by_pid = {
                int(s.player_id): (s.name or "") for s in scenario.player_spawns
            }
            # persona resolver: player_id(int) → (player_name, persona_block)。
            # gist prompt / promotion が persona を載せるために使う。
            _semantic_persona_resolver = (
                lambda pid_int, _n=_names_by_pid, _p=persona_block: (
                    _n.get(int(pid_int), ""),
                    _p,
                )
            )
            # gist は短期記憶 builder と同じく config.llm_client_kind で gate する
            # (config が stub なのに env 側で litellm が動く余地を残さない)。
            if _semantic_gist_enabled and config.llm_client_kind == "litellm":
                # R2c-1: full wiring 本体 (wiring/__init__) の private helper でなく、
                # 抽出済みの optional_llm_services から取る (= wiring/__init__ からの
                # symbol 依存を廃止)。import-time に wiring/__init__ がロードされる依存は
                # R2c-2 の __init__ 軽量化 (full wiring 本体削除) で解消する。
                from ai_rpg_world.application.llm.wiring.optional_llm_services import (
                    optional_semantic_gist_service,
                )
                from ai_rpg_world.application.llm.wiring._llm_client_factory import (
                    create_llm_client_from_config,
                )

                try:
                    _gist_client = create_llm_client_from_config(config)
                except Exception:
                    logger.exception(
                        "LLM client factory failed; semantic gist disabled"
                    )
                    _gist_client = None
                if _gist_client is not None:
                    _semantic_gist_service = optional_semantic_gist_service(
                        _gist_client, True
                    )
        # #526 / U3: 段1 (エピソード再解釈) の opt-in 配線。
        # LLM_EPISODIC_REINTERPRETATION_ENABLED かつ LiteLLMClient が取れるときだけ
        # completion port (= LLM) を渡す。flag ON でも client が stub なら completion
        # は None になり、coordinator は構築されるが再解釈 LLM は走らない
        # (prompt も recall_buffer を覗かない = graceful)。env 直読みせず config から取る。
        _reinterpretation_enabled = config.episodic_reinterpretation_enabled
        _reinterpretation_completion = None
        if _reinterpretation_enabled and config.llm_client_kind == "litellm":
            # R2c-1: 抽出済み optional_llm_services から取る (wiring/__init__ の
            # private helper symbol 依存を廃止。import-time 依存は R2c-2 で解消)。
            from ai_rpg_world.application.llm.wiring.optional_llm_services import (
                optional_episodic_reinterpretation_completion,
            )
            from ai_rpg_world.application.llm.wiring._llm_client_factory import (
                create_llm_client_from_config,
            )

            try:
                _reinterp_client = create_llm_client_from_config(config)
            except Exception:
                logger.exception(
                    "LLM client factory failed; episodic reinterpretation disabled"
                )
                _reinterp_client = None
            if _reinterp_client is not None:
                _reinterpretation_completion = (
                    optional_episodic_reinterpretation_completion(
                        _reinterp_client, None
                    )
                )
        # U3b: 固着パスの completion port。BELIEF_CONSOLIDATION_ENABLED かつ
        # litellm client が取れるときだけ実 LLM を配線する。client が stub
        # (llm_client_kind != "litellm") のときは coordinator 自体は構築される
        # が completion=None のまま (= flush が no-op、evidence は buffer に
        # 溜まり続けるだけの安全な縮退)。
        _belief_consolidation_completion = None
        if _belief_consolidation_enabled and config.llm_client_kind == "litellm":
            from ai_rpg_world.application.llm.wiring._llm_client_factory import (
                create_llm_client_from_config,
            )
            from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient

            try:
                _belief_consolidation_client = create_llm_client_from_config(config)
            except Exception:
                logger.exception(
                    "LLM client factory failed; belief consolidation disabled"
                )
                _belief_consolidation_client = None
            if isinstance(_belief_consolidation_client, LiteLLMClient):
                _belief_consolidation_completion = _belief_consolidation_client
        runtime._episodic_stack = build_episodic_stack(
            scenario=scenario,
            graph=spot_graph_repo.find_graph(),
            observation_buffer=obs_buffer,
            short_term_memory=short_term_memory,
            action_result_store=action_result_store,
            # trace_recorder は set_trace_recorder で後から差し込まれるので
            # provider 経由で参照。chunk 書き込みごとに
            # TraceEventKind.EPISODIC_CHUNK_WRITTEN が記録される。
            trace_recorder_provider=lambda: runtime._trace_recorder,
            current_tick_provider=runtime.current_tick,
            subjective_completion_scheduler=subjective_scheduler,
            persona_block_provider=persona_provider,
            # H-2 (自己言及ループ / 横断レビュー): chunk 主観補完が抽出した
            # heard_claims から「話者 = 聞き手本人」を弾くための本人名。
            # scenario.player_spawns から名前解決する既存 API を再利用する
            # (persona_block_provider と同じ player_id 引きの provider 形)。
            player_name_provider=runtime.get_player_name,
            episode_store=shared_episode_store,
            # semantic 有効時は link / promotion が build_episodic_memory_stack で
            # 組まれる (BeingId は各 caller 入口で渡す)。
            semantic_enabled=_semantic_enabled,
            semantic_passive_top_k=_semantic_top_k,
            semantic_gist_service=_semantic_gist_service,
            semantic_persona_resolver=_semantic_persona_resolver,
            reinterpretation_enabled=_reinterpretation_enabled,
            reinterpretation_completion=_reinterpretation_completion,
            # #526 段階 2: 慣化ペナルティ (default off)
            recall_habituation_enabled=config.recall_habituation_enabled,
            recall_habituation_decay_window_ticks=(
                config.recall_habituation_decay_window_ticks
            ),
            # #526 段階 3 + PR-A: 想起スロット (working memory / default off)
            recall_slot_enabled=config.recall_slot_enabled,
            recall_slot_capacity=config.recall_slot_capacity,
            recall_slot_insert_per_tick=config.recall_slot_insert_per_tick,
            recall_slot_max_residence=config.recall_slot_max_residence,
            recall_slot_cooldown_ticks=config.recall_slot_cooldown_ticks,
            recall_slot_insert_score_threshold=(
                config.recall_slot_insert_score_threshold
            ),
            # #526 段階 3 PR-C: afterglow index (= ぼんやり覚えてる 1 行見出し)
            afterglow_enabled=config.afterglow_enabled,
            afterglow_capacity=config.afterglow_capacity,
            afterglow_max_residence=config.afterglow_max_residence,
            # #526 後続 C1: spot_interior_repo を渡し、noun_matcher が
            # world_object 名を index できるようにする。SpotNode.interior は
            # 実 runtime では None で保管され、別 repository に格納されている。
            spot_interior_repo=spot_interior_repo,
            # #526 後続 C2: chunk write 時の player 現在状況 (場所 / 視界 object
            # / 同席者) を episode の固定 cue として焼き付けるための provider。
            # runtime.build_llm_context(pid).tool_runtime_context を返す lambda
            # を渡す。例外ハンドリングは builder 側で graceful に行う。
            runtime_context_provider=lambda pid: runtime.build_llm_context(
                pid
            ).tool_runtime_context,
            # U2 (証拠台帳統一設計): 同期経路用に transcriber を渡す (実際に
            # 発火するのは chunk_subjective_fields_service 注入時のみ。本
            # runtime の既定経路は非同期 scheduler なので通常は素通り)。store
            # 自体は snapshot 用に stack へ公開する。
            belief_evidence_transcriber=belief_evidence_transcriber,
            belief_evidence_buffer_store=belief_evidence_buffer_store,
            # U3b (固着パス): default OFF。ON のときのみクラスタ昇格が
            # FAMILIARITY 転用モードになり、BeliefConsolidationCoordinator が
            # 構築される。
            belief_consolidation_enabled=_belief_consolidation_enabled,
            belief_consolidation_completion=_belief_consolidation_completion,
            # U4 (予測誤差統一設計 部品3): 同期経路 (chunk_coordinator) 用。
            # 非同期経路 (scheduler) には上で個別に渡し済み。
            belief_attribution_enabled=_belief_attribution_enabled,
            # P4 (reflect): 固着 LLM に目的への前進評価を足す。監査対象の目的文と
            # 内省観測 sink を provider で渡す (goal store 差し替えは P7)。
            goal_reflect_enabled=_goal_reflect_enabled,
            objective_text_provider=runtime._reflect_objective_provider,
            reflect_observation_sink=runtime._emit_reflect_observation,
            # P-U1 (目的停滞の evidence 化): ON のときだけ stalled/misaligned の
            # reflect verdict を goal: 軸の高 salience evidence に変換する。
            goal_stagnation_evidence_enabled=_goal_stagnation_evidence_enabled,
            # P-U2 (停滞感 store): ON のときだけ reflect verdict を停滞感カウンタ
            # に畳み込む。store は上で構築済み (runtime._stagnation_pressure_store)。
            stagnation_pressure_enabled=_stagnation_pressure_enabled,
            stagnation_pressure_store=runtime._stagnation_pressure_store,
            # P10 (伝聞の固着判断): ON のとき固着 LLM に伝聞節を足し、shortlist に
            # 話者 belief を載せ、HEARSAY 支持を confidence 半分に数える。抽出側
            # (P9) と同じ HEARSAY_ENABLED で連動させる (抽出だけ ON で固着側が
            # 素通しになる中途半端な状態を作らない)。
            hearsay_enabled=_hearsay_enabled,
            # U9a (誤差駆動再解釈): 同期経路 (chunk_coordinator) 用。非同期経路
            # (scheduler) は recall_buffer 確定後に下で set_recall_buffer_store
            # を呼んで差し込む (scheduler 自体は build_episodic_stack より先に
            # 構築済のため、コンストラクタでは渡せない)。
            error_driven_reinterpretation_enabled=(
                _error_driven_reinterpretation_enabled
            ),
            # U8 (部品2a): chunk_coordinator (同期・非同期共通の境界判定) に
            # decide_chunk_boundary への flag 伝播を頼む。
            error_gated_boundary_enabled=_error_gated_encoding_enabled,
            # U9b (想起の信用割り当て・的中側): 同期経路 (chunk_coordinator) と
            # passive_recall 両方に的中側 sidecar を配線する。非同期経路
            # (scheduler) は recall_success_store 確定後に下で
            # set_recall_success_store を呼んで差し込む。
            recall_hit_boost_enabled=_recall_hit_boost_enabled,
            recall_hit_boost_strength=_recall_hit_boost_strength,
            # U10a (pending prediction): 同期経路 (chunk_coordinator) と
            # store 自体の構築を build_episodic_stack に任せる。非同期経路
            # (scheduler) は下で set_pending_prediction_store により差し込む。
            pending_prediction_enabled=_pending_prediction_enabled,
            episodic_promotion_force_full_scan=(
                config.episodic_promotion_force_full_scan
            ),
            episodic_promotion_expansion_hops=(
                config.episodic_promotion_expansion_hops
            ),
            # episode store の永続化先。subjective 経路は shared_episode_store を
            # 先に組んで渡すため resolve_default はそれを尊重する (db_path 未使用)。
            # config の __post_init__ が「db_path + subjective」の無視組み合わせを
            # fail-fast 済みなので、ここに来る db_path は非 subjective 経路のみ。
            subjective_episode_db_path=config.subjective_episode_db_path,
        )

        # U9a: recall_buffer を scheduler に後から差し込む。
        # subjective_scheduler は build_episodic_stack より先に構築されている
        # ため (Pattern A の episode_store 共有と同じ理由)、recall_buffer が
        # 確定するこの時点で set_recall_buffer_store により差し込む。
        # ``recall_buffer_store`` は reinterpretation_completion が無いと None
        # のまま (= 再解釈 LLM が走らず stamp しても意味が無いので同じ条件で
        # 縮退させる)。
        if subjective_scheduler is not None:
            subjective_scheduler.set_recall_buffer_store(
                runtime._episodic_stack.recall_buffer_store
            )
            # U9b: recall_success_store も同じ理由で後から差し込む。
            subjective_scheduler.set_recall_success_store(
                runtime._episodic_stack.recall_success_store
            )
            # U10a: pending_prediction_store も同じ理由で後から差し込む。
            subjective_scheduler.set_pending_prediction_store(
                runtime._episodic_stack.pending_prediction_store
            )

        # U7: 無意識コンテキスト用 semantic recall service を確定させる。
        # build_episodic_stack が semantic_enabled=True のときに初めて
        # semantic_memory_store を構築するため (この関数のずっと上、subjective
        # service 構築時点ではまだ存在しない)、ここで holder に実体を積む。
        # provider (build_unconscious_context_provider が返す closure) は
        # 呼ばれる瞬間にこの holder を見るので、以降の chunk 補完から belief が
        # 引けるようになる。semantic_memory_store が None (= 何らかの理由で
        # semantic スタックが組まれなかった) なら holder は None のままで、
        # provider は belief 無し (空文字) に安全に縮退する。
        if (
            _unconscious_context_enabled
            and runtime._episodic_stack.semantic_memory_store is not None
        ):
            from ai_rpg_world.application.llm.services.semantic_passive_recall_service import (
                SemanticPassiveRecallService,
            )

            _unconscious_context_semantic_recall_holder[0] = SemanticPassiveRecallService(
                runtime._episodic_stack.semantic_memory_store,
            )

        # U6 (STRUCTURED_FAILURE): flag ON のときだけ transcriber を作り
        # runtime に公開する。runtime_manager (presentation 層) が
        # tool_call_loop_guard.record_and_check() の戻り値
        # (CrossTickFailureTrigger) を見て being_id を解決し、本 transcriber
        # を呼ぶ (= loop_guard 自身は being 解決ロジックを持たない設計)。
        # episode_store は build_episodic_stack が確定させた共有 store
        # (subjective 未配線時も内部で新規生成されるため必ず非 None)。
        runtime._structured_failure_transcriber = None
        if _salience_structured_failure_enabled and belief_evidence_buffer_store is not None:
            from ai_rpg_world.application.llm.services.structured_failure_evidence_transcriber import (
                StructuredFailureEvidenceTranscriber,
            )

            runtime._structured_failure_transcriber = (
                StructuredFailureEvidenceTranscriber(
                    belief_evidence_buffer_store,
                    runtime._episodic_stack.episode_store,
                    trace_recorder_provider=lambda: runtime._trace_recorder,
                    current_tick_provider=runtime.current_tick,
                )
            )

        # PR-D (STATE_COLLAPSE): flag ON のときだけ transcriber を作り、
        # 1) PlayerDownedEvent / PlayerRevivedEvent の side handler として
        #    pipeline_event_publisher に登録する (is_down 遷移フック)
        # 2) needs_decay_stage に後付け注入する (hunger max 到達フック)
        # being 解決は世界内で 1 か所に閉じる (aux_being_resolver 経由)。
        if _state_collapse_evidence_enabled and belief_evidence_buffer_store is not None:
            from ai_rpg_world.application.llm.services.state_collapse_evidence_transcriber import (
                StateCollapseEvidenceTranscriber,
            )
            from ai_rpg_world.application.player.handlers.player_downed_state_collapse_evidence_handler import (
                PlayerDownedStateCollapseEvidenceHandler,
            )
            from ai_rpg_world.application.player.handlers.player_revived_state_collapse_evidence_handler import (
                PlayerRevivedStateCollapseEvidenceHandler,
            )

            state_collapse_transcriber = StateCollapseEvidenceTranscriber(
                belief_evidence_buffer_store,
                runtime._episodic_stack.episode_store,
                trace_recorder_provider=lambda: runtime._trace_recorder,
                current_tick_provider=runtime.current_tick,
            )

            def _resolve_state_collapse_being_id(
                player_id: PlayerId,
            ) -> Optional[BeingId]:
                resolver = getattr(runtime, "_aux_being_resolver", None)
                world_id = getattr(runtime, "_aux_being_default_world_id", None)
                if resolver is None or world_id is None:
                    return None
                return resolver.resolve_being_id(world_id, player_id)

            pipeline_event_publisher.register_handler(
                PlayerDownedEvent,
                PlayerDownedStateCollapseEvidenceHandler(
                    transcriber=state_collapse_transcriber,
                    being_id_resolver=_resolve_state_collapse_being_id,
                ),
            )
            pipeline_event_publisher.register_handler(
                PlayerRevivedEvent,
                PlayerRevivedStateCollapseEvidenceHandler(
                    transcriber=state_collapse_transcriber,
                    being_id_resolver=_resolve_state_collapse_being_id,
                ),
            )
            needs_decay_stage.set_state_collapse_evidence_wiring(
                state_collapse_transcriber, _resolve_state_collapse_being_id
            )

        # U5 (MEMO_DISTILL): flag ON のときだけ transcriber を作り、既に
        # 構築済の _todo_tool_executor (= _wire_auxiliary_tool_stack() が本
        # ブロックより前で呼ばれるため belief_evidence_buffer_store 確定前に
        # 作られている) へ post-hoc に差し込む。executor 自身が memo_done
        # 成功時に record_from_memo を呼ぶ (loop_guard 経由の STRUCTURED_FAILURE
        # と異なり presentation 層の仲介は不要)。episode_store は
        # build_episodic_stack が確定させた共有 store。
        if _memo_distill_enabled and belief_evidence_buffer_store is not None:
            from ai_rpg_world.application.llm.services.memo_distill_evidence_transcriber import (
                MemoDistillEvidenceTranscriber,
            )

            memo_distill_transcriber = MemoDistillEvidenceTranscriber(
                belief_evidence_buffer_store,
                runtime._episodic_stack.episode_store,
                trace_recorder_provider=lambda: runtime._trace_recorder,
                current_tick_provider=runtime.current_tick,
            )
            # runtime に保持し、以後 _wire_auxiliary_tool_stack が executor を
            # 作り直しても (set_trace_recorder 等) 再適用されるようにする。
            # これがないと build 後の set_trace_recorder で transcriber が
            # 静かに失われていた (memo_done 28 件に対し evidence 0 件)。
            runtime._memo_distill_transcriber = memo_distill_transcriber
            if runtime._todo_tool_executor is not None:
                runtime._todo_tool_executor.set_memo_distill_transcriber(
                    memo_distill_transcriber
                )

    # PR #451 (PR 6/6): LLM 経路は _build_short_term_memory の ctor 注入で
    # 既に揃っている。旧 _wire_short_term_llm_services による setter 後注入は廃止
    # (setter 呼び忘れ silent failure を構造で排除)。

    # disabled_tools の名前が実在するかを、ここで確かめる。
    #
    # 判定自体は get_tool_definitions が持っているが、それを待つと
    # presentation 層の起動時検査まで遅れる。**シナリオの書き間違いは
    # シナリオを読んだ直後に落としたい。** run を 1 本流し終えてから
    # 「無効化したつもりが出たままだった」と気付くのが最悪の形。
    runtime._validate_disabled_tool_names()
    runtime._validate_action_argument_classification_at_startup()
    runtime._validate_prompt_argument_contract_at_startup()
    return runtime


# PR #451 (PR 6/6): _wire_short_term_llm_services は廃止。
# 旧来は ctor で空殻 (summary_service=None) を作り、後で setter 注入する 2 段階
# 構築だったが、setter 呼び忘れで silent failure を量産 (PR #444 の実害)。
# 本 PR で _build_short_term_memory に統合し ctor 一発注入に変更したため、
# 後注入用のこの helper は不要になった。
