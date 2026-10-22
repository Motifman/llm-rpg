"""LLM エージェントが世界で生きる汎用ランタイム (world_runtime)。

シナリオ JSON → インメモリリポジトリ → アプリケーションサービス をワイヤリングし、
プログラム的にアクションを実行できるようにする。escape ゲーム・survival 等のジャンルに
依存せず、勝敗のない永続世界も含めて同じ turn 実行経路で動かす (経路統一 層1)。

LLM エージェントが**実際に**受け取る観測テキスト・ツール定義・ラベル解決コンテキストを
そのまま可視化する。デモ専用の加工は行わない。
"""

from __future__ import annotations

import logging
import random
import threading
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

if TYPE_CHECKING:
    from ai_rpg_world.application.being.being_attachment_resolver import (
        BeingAttachmentResolver,
    )
    from ai_rpg_world.application.llm.services.prompt_builder import DefaultPromptBuilder
    from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
        ResolvedLlmRuntimeConfig,
    )
    from ai_rpg_world.application.player.services.departed_position_store import (
        DepartedPositionStore,
    )
    from ai_rpg_world.application.player.services.fallen_body_registry import (
        FallenBodyRegistry,
    )
    from ai_rpg_world.application.player.services.player_perception_policy import (
        PlayerPerceptionPolicy,
    )
    from ai_rpg_world.application.world_graph.interaction_cooldown_store import (
        InteractionCooldownStore,
    )
    from ai_rpg_world.application.world_graph.player_interaction_application_service import (
        PlayerInteractionApplicationService,
    )
    from ai_rpg_world.application.world_graph.world_tick_failure_isolation import (
        WorldTickFailureIsolator,
    )
    from ai_rpg_world.domain.being.value_object.being_id import BeingId
    from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
        WorldGraphEffectService,
    )

logger = logging.getLogger(__name__)


def _new_interaction_cooldown_store() -> Any:
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


from ai_rpg_world.application.being.acting_being import ActingBeing
from ai_rpg_world.application.being.player_acquaintances import PlayerAcquaintances
from ai_rpg_world.application.encounter.in_memory_encounter_memory import (
    InMemoryEncounterMemory,
)
from ai_rpg_world.application.encounter.services.encounter_observation_collector import (
    EncounterObservationCollector,
)
from ai_rpg_world.application.llm.contracts.action_argument_classification import (
    ActionArgumentClassificationError,
    unclassified_action_argument_names,
)
from ai_rpg_world.application.llm.contracts.aux_llm_call import AuxLlmCallSink
from ai_rpg_world.application.llm.contracts.dtos import (
    LlmCommandResultDto,
    LlmUiContextDto,
    ToolDefinitionDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.contracts.interfaces import ILlmTurnTrigger, IShortTermMemory
from ai_rpg_world.application.llm.services.action_result_recorder import ActionResultRecorder
from ai_rpg_world.application.llm.services.action_result_store import DefaultActionResultStore
from ai_rpg_world.application.llm.services.action_summary_format import (
    project_action_arguments_for_history,
)
from ai_rpg_world.application.llm.services.context_format_strategy import (
    SectionBasedContextFormatStrategy,
)
from ai_rpg_world.application.llm.services.prompt_argument_contract import (
    PromptArgumentContractError,
    PromptArgumentContractViolation,
    find_prompt_argument_contract_violations,
)
from ai_rpg_world.application.llm.services.recent_events_formatter import DefaultRecentEventsFormatter
from ai_rpg_world.application.llm.services.spot_graph_current_state_formatter import (
    SpotGraphCurrentStateFormatter,
)
from ai_rpg_world.application.llm.services.spot_graph_ui_context_builder import (
    SpotGraphUiContextBuilder,
)
from ai_rpg_world.application.llm.services.tool_catalog.memo_argument import (
    with_memo_schema,
)
from ai_rpg_world.application.llm.services.tool_catalog.memory import (
    get_memory_specs,
)
from ai_rpg_world.application.llm.services.tool_catalog.public_sns import get_public_sns_definitions
from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import get_spot_graph_specs
from ai_rpg_world.application.llm.services.tool_catalog.subjective_action import (
    assess_situation_definition,
    strip_reason_first_action_subjective_schema,
)
from ai_rpg_world.application.llm.services.unified_recent_event_store import (
    UnifiedRecentEventStore,
)
from ai_rpg_world.application.llm.services.world_briefing import (
    build_own_state_display_names,
    build_recorded_player_state_tick_keys,
    build_world_briefing,
)
from ai_rpg_world.application.llm.services.world_llm_prompt import (
    CharacterPromptInput,
    build_persona_block_from_character,
    build_world_system_prompt,
    safe_world_intro_text,
)
from ai_rpg_world.application.llm.services.world_llm_turn.llm_failure_streak_monitor import (
    DEFAULT_FAILURE_STREAK_ABORT,
    LlmFailureStreakMonitor,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_EPISODE_RECALL,
    TOOL_NAME_EPISODE_REVISE_INDEX,
    TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
)
from ai_rpg_world.application.llm.tool_exposure import ToolExposure
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationOutput,
    SubjectUnknownView,
    WithheldFromStrangers,
)
from ai_rpg_world.application.observation.services.heartbeat_observation_emitter import (
    HeartbeatObservationEmitter,
)
from ai_rpg_world.application.observation.services.observation_appender import (
    ObservationAppender,
)
from ai_rpg_world.application.observation.services.observation_context_buffer import DefaultObservationContextBuffer
from ai_rpg_world.application.observation.services.observation_formatter import ObservationFormatter
from ai_rpg_world.application.observation.services.observation_pipeline import ObservationPipeline
from ai_rpg_world.application.observation.services.observation_recipient_resolver import (
    create_observation_recipient_resolver,
)
from ai_rpg_world.application.observation.services.observation_turn_scheduler import (
    ObservationTurnScheduler,
)
from ai_rpg_world.application.player.services.player_life_query import PlayerLifeQuery
from ai_rpg_world.application.player.services.player_outcome_observation_formatter import (
    PlayerOutcomeObservationFormatter,
)
from ai_rpg_world.application.social.public_sns.retained_screen import PublicSnsScreenStore
from ai_rpg_world.application.speech.contracts.commands import SpeakCommand
from ai_rpg_world.application.speech.services.player_speech_service import (
    PlayerSpeechApplicationService,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trade.services.in_memory_market_board_store import (
    InMemoryMarketBoardStore,
)
from ai_rpg_world.application.trade.services.in_memory_pending_trade_offer_store import (
    InMemoryPendingTradeOfferStore,
)
from ai_rpg_world.application.trade.services.market_order_expiry_stage import (
    MarketOrderExpiryStage,
)
from ai_rpg_world.application.trade.services.market_service import MarketService
from ai_rpg_world.application.trade.services.player_trade_service import (
    PlayerTradeService,
)
from ai_rpg_world.application.trade.services.trade_freeze_service import (
    TradeFreezeService,
)
from ai_rpg_world.application.trade.services.trade_offer_expiry_stage import (
    TradeOfferExpiryStage,
)
from ai_rpg_world.application.world.contracts.dtos import PlayerCurrentStateDto
from ai_rpg_world.application.world_graph.distant_view_service import (
    DistantViewArea,
    DistantViewCandidate,
    DistantViewConnection,
    DistantViewService,
    DistantViewSpot,
    DistantViewVisibleCandidate,
)
from ai_rpg_world.application.world_graph.game_phase_store import GamePhaseStore
from ai_rpg_world.application.world_graph.meeting_command_service import (
    MeetingCommandService,
    MeetingOngoingCondition,
)
from ai_rpg_world.application.world_graph.overflow_sinks import (
    GroundOverflowSink,
    refuse_overflow,
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
from ai_rpg_world.application.world_graph.spot_exploration_application_service import (
    SpotExplorationApplicationService,
    SpotExplorationResultDto,
)
from ai_rpg_world.application.world_graph.spot_exploration_progress_store import (
    InMemorySpotExplorationProgressStore,
)
from ai_rpg_world.application.world_graph.spot_graph_current_state_builder import (
    SpotGraphCurrentStateBuilder,
)
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphInventoryItemEntry,
)
from ai_rpg_world.application.world_graph.spot_graph_day_night_stage_service import (
    SpotGraphDayNightStageService,
)
from ai_rpg_world.application.world_graph.spot_graph_environment_stage_service import (
    SpotGraphEnvironmentStageService,
)
from ai_rpg_world.application.world_graph.spot_graph_item_transfer_service import (
    ItemTransferResult,
    SpotGraphItemTransferService,
)
from ai_rpg_world.application.world_graph.spot_graph_merchant_trade_service import (
    SpotGraphMerchantTradeService,
)
from ai_rpg_world.application.world_graph.spot_graph_movement_application_service import (
    SpotGraphMovementApplicationService,
    SpotTravelBlocked,
)
from ai_rpg_world.application.world_graph.spot_graph_needs_decay_stage_service import (
    SpotGraphNeedsDecayStageService,
)
from ai_rpg_world.application.world_graph.spot_graph_scenario_event_progress_store import (
    InMemorySpotGraphScenarioEventProgressStore,
)
from ai_rpg_world.application.world_graph.spot_graph_scenario_event_stage_service import (
    SpotGraphScenarioEventStageService,
)
from ai_rpg_world.application.world_graph.spot_graph_simulation_application_service import (
    SpotGraphSimulationApplicationService,
)
from ai_rpg_world.application.world_graph.spot_graph_travel_context import (
    SpotGraphTravelContextProvider,
)
from ai_rpg_world.application.world_graph.spot_graph_travel_stage_service import (
    SpotGraphTravelStageService,
)
from ai_rpg_world.application.world_graph.spot_interaction_application_service import (
    SpotInteractionApplicationService,
    SpotInteractionResultDto,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    collect_owned_item_spec_ids_from_inventory,
    grant_initial_items_to_inventory,
)
from ai_rpg_world.application.world_graph.synchronized_action_registry import (
    SynchronizedActionRegistry,
)
from ai_rpg_world.application.world_graph.synchronized_action_resolver_stage_service import (
    SynchronizedActionResolverStageService,
)
from ai_rpg_world.application.world_graph.travel_blocked_message import (
    travel_blocked_cue,
)
from ai_rpg_world.application.world_graph.world_flag_state import (
    MutableWorldFlagState,
    WorldFlagChange,
    WorldFlagMutationContext,
    WorldFlagMutationSource,
)
from ai_rpg_world.application.world_runtime.pipeline_event_publisher import PipelineEventPublisher
from ai_rpg_world.being.domain.acquaintance import AcquaintanceRepository
from ai_rpg_world.being.domain.episode import EpisodeRepository
from ai_rpg_world.being.domain.memo_book import MemoBookRepository
from ai_rpg_world.being.domain.memory_turn_clock import MemoryTurnClock, MemoryTurnReader
from ai_rpg_world.being.infrastructure.in_memory_acquaintance_repository import (
    InMemoryAcquaintanceRepository,
)
from ai_rpg_world.being.infrastructure.in_memory_episode_repository import (
    InMemoryEpisodeRepository,
)
from ai_rpg_world.being.infrastructure.in_memory_memo_book_repository import (
    InMemoryMemoBookRepository,
)
from ai_rpg_world.being.infrastructure.in_memory_memory_turn_clock import (
    InMemoryMemoryTurnClock,
)
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.memory.encounter.value_object.encounter_key import (
    EncounterKey,
)
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.enum.player_enum import AttentionLevel, SpeechChannel
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_navigation_state import PlayerNavigationState
from ai_rpg_world.domain.player.value_object.player_spot_navigation_state import PlayerSpotNavigationState
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.domain.trade.value_object.market_reach import (
    MarketReach,
)
from ai_rpg_world.domain.world.value_object.coordinate import Coordinate
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.enum.game_result_enum import GameResultEnum
from ai_rpg_world.domain.world_graph.enum.meeting_trigger import (
    MeetingEndReason,
    MeetingStartTrigger,
)
from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import GameEndConditionEvaluator
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.game_end_result import GameEndResult
from ai_rpg_world.domain.world_graph.value_object.scenario_event_def import ScenarioEventDef
from ai_rpg_world.domain.world_graph.value_object.scenario_team import (
    decide_team_results,
)
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.world_flag_registry import WorldFlagRegistry
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import InMemoryItemRepository
from ai_rpg_world.infrastructure.repository.in_memory_item_spec_repository import InMemoryItemSpecRepository
from ai_rpg_world.infrastructure.repository.in_memory_monster_aggregate_repository import (
    InMemoryMonsterAggregateRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_monster_template_repository import (
    InMemoryMonsterTemplateRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import InMemoryPlayerStatusRepository
from ai_rpg_world.infrastructure.repository.in_memory_skill_loadout_repository import (
    InMemorySkillLoadoutRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import InMemorySpotGraphRepository
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import InMemorySpotInteriorRepository
from ai_rpg_world.infrastructure.scenario.models import ScenarioDayNightConfig
from ai_rpg_world.infrastructure.scenario.scenario_id_mapper import ScenarioIdMapper
from ai_rpg_world.infrastructure.scenario.scenario_loader import (
    PlayerSpawnConfig,
    ScenarioLoader,
    ScenarioLoadResult,
    ScenarioMetadata,
)
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
    InMemoryGameTimeProvider,
)


def _optional_kwarg(name: str, value: Any) -> dict[str, Any]:
    """値が None なら渡さない。既定値を 2 箇所に置かないための補助。"""
    return {} if value is None else {name: value}


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


def _minutes_per_tick(scenario: ScenarioLoadResult) -> int | None:
    """1 tick が世界の時計で何分か。

    現在時刻の表示 (`深夜 0:05`) と同じ換算を使う。エージェントはその時計を
    毎ターン見ているので、**同じ単位で書けばアリバイの検算がそのままできる**。

    昼夜サイクルを宣言していない世界は ``_time_label`` と同じ 5 分/tick に
    倒す。時計だけ進んで地図が別単位、という食い違いを作らない。
    """
    day_night = scenario.day_night_config
    if day_night is None:
        return _FALLBACK_MINUTES_PER_TICK
    return (24 * 60) // day_night.cycle.ticks_per_day


def _required_task_count(scenario: Any) -> int | None:
    """勝利条件が要求する点検の数。宣言が無ければ None。

    **手書きの数字と食い違わせないため、勝ち筋もデータから読む。**
    """
    for condition in getattr(scenario, "win_conditions", ()) or ():
        count = getattr(condition, "min_set_count", None)
        if isinstance(count, int) and not isinstance(count, bool):
            return count
    return None


def _scenario_has_goal(scenario: ScenarioLoadResult) -> bool:
    """勝敗条件を宣言するシナリオか (= goal あり) を導出する (#526 U5)。

    win/lose/end/player outcome 規則のいずれかがあれば goal 前提の文面にする。
    既存シナリオは全て game_end_conditions を持つので True になり、system
    prompt の挙動は不変。

    個人結果規則を持つ島シナリオも含めるのが必須。win/lose 配列だけを見ると
    「勝敗条件なしの open world」に誤判定される。
    """
    return bool(
        scenario.win_conditions
        or scenario.lose_conditions
        or scenario.end_conditions
        or scenario.player_outcome_rules
    )


@dataclass
class WorldRuntime:
    """LLM エージェントが世界で生きる汎用ランタイム（全てインメモリ）。"""

    scenario: ScenarioLoadResult
    _spot_graph_repo: InMemorySpotGraphRepository
    _spot_interior_repo: InMemorySpotInteriorRepository
    _player_status_repo: InMemoryPlayerStatusRepository
    _player_life_query: PlayerLifeQuery
    _player_perception_policy: PlayerPerceptionPolicy
    _fallen_body_registry: FallenBodyRegistry
    _departed_position_store: DepartedPositionStore
    _player_inventory_repo: InMemoryPlayerInventoryRepository
    _item_repo: InMemoryItemRepository
    _item_spec_repo: InMemoryItemSpecRepository
    _world_flag_state: MutableWorldFlagState
    _effect_service: WorldGraphEffectService
    _exploration_progress: InMemorySpotExplorationProgressStore
    _movement_service: SpotGraphMovementApplicationService
    _interaction_service: SpotInteractionApplicationService
    _player_interaction_service: PlayerInteractionApplicationService
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
    _day_night_stage: SpotGraphDayNightStageService | None = field(default=None, repr=False)
    # #344 配線漏れ修正: spot_graph_use_item / attack / give_item / pickup_item /
    # drop_item / prepare_action を experiment runtime 経路で動かすため、
    # ToolExecutor が必要とする monster_repo と attack_orchestrator も runtime に
    # 保持する (factory function が代入する)。monster が居ないシナリオでは None。
    _monster_repo: Any = field(default=None, repr=False)
    _attack_orchestrator: Any = field(default=None, repr=False)
    # Phase E-3: プレイヤー個別 outcome の registry (PlayerId → PlayerOutcomeEnum)。
    # factory は PlayerLifeQuery と同じ instance を構築時に渡す。
    _player_outcome_registry: Any | None = field(default=None, repr=False)
    _public_sns_data_store: Any = field(default=None, repr=False)
    _public_sns_read_service: Any = field(default=None, repr=False)
    _public_sns_command_service: Any = field(default=None, repr=False)
    _public_sns_executor: Any = field(default=None, repr=False)
    _public_sns_projection: Any = field(default=None, repr=False)
    _public_sns_screens: PublicSnsScreenStore = field(default_factory=PublicSnsScreenStore, repr=False)
    _execution_turns: dict[int, int] = field(default_factory=dict, repr=False)
    _tick: int = 0
    # #375 後続: 食料腐敗の日次集約バッファ (code-review HIGH 指摘)。
    # hasattr ベースの遅延初期化だと IDE/mypy / pickle で扱いにくいので
    # dataclass field として明示宣言する。
    # key: spec_id → {"spec_id", "spec_name", "instance_ids": [...]}
    _pending_spoiled: dict[int, dict[str, Any]] = field(default_factory=dict, repr=False)
    # 現在 buffer に積まれている食料が属する day (= tick // ticks_per_day)。
    # None は「buffer 空 + 1 件もまだ来ていない」。
    _pending_spoiled_day: int | None = field(default=None, repr=False)
    # 段階3: 動的遠景 cue の false→true 境界検出状態。
    # per-world の事実なので player ごとではなく runtime に保持し、snapshot
    # で保存する。値は {"active": bool, "initialized": bool,
    # "last_changed_tick": int | None}。
    _distant_cue_states: dict[str, dict[str, Any]] = field(
        default_factory=dict, repr=False
    )
    # 世界のフェーズ (自由時間 / 会議)。per-world。会議・投票の土台
    # (docs/memory_system/meeting_and_voting_design.md §2.1)。
    # 常にちょうど 1 つのフェーズを持ち、排他は store の遷移メソッドが守る。
    _game_phase_store: GamePhaseStore = field(
        default_factory=lambda: GamePhaseStore(), repr=False
    )
    # 対人行為の再使用間隔。per-world。tick 基準で PlayerId をキーにするので
    # Being ではなく world snapshot に載る (codec を同じ PR で入れてある)。
    _interaction_cooldown_store: InteractionCooldownStore = field(
        default_factory=lambda: _new_interaction_cooldown_store(), repr=False
    )
    # 会議機構を使うシナリオか (scenario の `meeting` block 由来)。
    # False なら招集・投票の tool を出さず、runtime のメソッドも拒否する。
    # 宣言していない世界のプロンプトを 1 バイトも変えないための切り分け。
    _meeting_enabled: bool = field(default=False, repr=False)
    _meeting_command_service: MeetingCommandService | None = field(
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
    _world_llm_system_prompts_by_player_id: dict[int, str] = field(
        default_factory=dict, repr=False
    )
    # create_world_runtime が構築後に差し込む配線。型は circular import 回避で
    # Any。宣言が無いと、代入側の typo を静かに受け入れてしまう。
    _use_item_command_scope_factory: Any | None = field(default=None, repr=False)
    _tend_to_player_command_scope_factory: Any | None = field(default=None, repr=False)
    _prepare_action_command_scope_factory: Any | None = field(default=None, repr=False)
    _death_grace_timer: Any | None = field(default=None, repr=False)
    _downed_incident_log: Any | None = field(default=None, repr=False)
    # #1631: Being ごとの記憶のターン数。1 手ごとに進め、記憶にターン数を付ける
    # 部品はここから読む。あとから代入し直すと、先に組んだ部品だけが古い時計を
    # 読み続ける。
    _memory_turn_clock: MemoryTurnClock = field(
        default_factory=InMemoryMemoryTurnClock, repr=False
    )
    # #1520: Being が会った相手の記録。Being の snapshot に入り、世界の
    # snapshot には入らない。
    _acquaintance_store: AcquaintanceRepository = field(
        default_factory=InMemoryAcquaintanceRepository, repr=False
    )
    _player_acquaintances: PlayerAcquaintances | None = field(
        default=None, repr=False
    )
    # #1623: 知り合いの記録と同じく、世界の snapshot には入らない。
    _being_episode_store: EpisodeRepository = field(
        default_factory=InMemoryEpisodeRepository, repr=False
    )
    # #1626: profile で書き起こしを有効にしたときだけ create_world_runtime が組む。
    _player_episode_writing: Any | None = field(default=None, repr=False)
    # #1623: profile で目次を出す設定にしたときだけ create_world_runtime が組む。
    _being_episode_recall_tool_executor: Any | None = field(default=None, repr=False)
    _being_episode_index_revision_tool_executor: Any | None = field(default=None, repr=False)
    # #1628: エピソードと同じく、世界の snapshot には入らない。
    _being_memo_store: MemoBookRepository = field(
        default_factory=InMemoryMemoBookRepository, repr=False
    )
    # reason-first 2段階 turn の有効化。True でも常時 2 段階ではなく、
    # presentation runtime_manager の Phase A 入口で既存 shared state を読んで
    # gated 発火する。下流 execution / episode / prediction 経路は mode 非分岐。
    reason_first_two_step_enabled: bool = field(default=False, repr=False)
    # シナリオ実行 trace の recorder。未設定なら NullTraceRecorder にフォールバック
    # (Phase 1d 配線)。
    _trace_recorder: Any = field(default=None, repr=False)
    # 記憶の部品と Jev の呼び出しの記録先 (#1617)。runtime の外で組む Jev も
    # ここを通すので、create_world_runtime 以外で組んだ runtime では None。
    _aux_llm_call_sink: Any = field(default=None, repr=False)
    _world_tick_failure_isolator: WorldTickFailureIsolator | None = field(default=None, repr=False)
    # trace 用の run 内集計。世界状態ではなく観測値なので snapshot へは載せない。
    _cumulative_travel_ticks_by_player: dict[int, int] = field(
        default_factory=dict, repr=False
    )
    _cumulative_meeting_ticks: int = field(default=0, repr=False)
    # 実験設定の解決済み DTO。遅延構築される component も env を読み直さず、
    # runtime 作成時と同じ設定を見るために保持する。
    _runtime_config: Any | None = field(default=None, repr=False)
    # PR 2 (#227): speech 配信経路統一。PlayerSpokeEvent をドメインイベント
    # として fire し、ObservationPipeline → buffer 経路で配信する。直接
    # broadcast (旧 _append_agent_speech) は廃止。
    _speech_service: PlayerSpeechApplicationService | None = field(
        default=None, repr=False
    )
    _speech_event_publisher: PipelineEventPublisher | None = field(
        default=None, repr=False
    )
    _observation_appender: ObservationAppender | None = field(default=None, repr=False)
    # turn_scheduler はセッション作成時に create_session で注入される
    # (LlmTurnTrigger と llm_player_resolver は wiring で組み立てる必要があるため)
    _observation_turn_scheduler: ObservationTurnScheduler | None = field(
        default=None, repr=False
    )
    # #404 fix: travel_stage を runtime に保持する。create_session 経路から
    # 「到着時の schedule_turn コールバック」を後付けで注入するため、参照を
    # 露出させる必要がある (simulation_service の中に隠れたままだと外から
    # 触れない)。
    _travel_stage: SpotGraphTravelStageService | None = field(default=None, repr=False)
    # #404 P2 (progress 可観測性): driver iteration 内で発火した LLM 呼び出し回数を
    # 集計する単純カウンタ。``_LlmMetricsTraceSink.record`` が bump し、experiment
    # progress reporter が iteration 終端で snapshot + reset する。Phase A の
    # ThreadPoolExecutor で並行 increment され得るため Lock で保護する。
    _llm_call_count: int = field(default=0, repr=False)
    _llm_call_count_lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False
    )
    # 連続失敗による run 停止 (層 2)。`_runtime_config` から閾値を読んで遅延
    # 生成する。設定を持たない runtime (presentation 単体テスト等) でも
    # 既定値で動くので、配線漏れが「監視が黙って無効」にならない。
    _llm_failure_monitor: LlmFailureStreakMonitor | None = field(
        default=None, repr=False
    )
    _llm_failure_monitor_lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False
    )

    @property
    def id_mapper(self) -> ScenarioIdMapper:
        return self.scenario.id_mapper

    @property
    def metadata(self) -> ScenarioMetadata:
        return self.scenario.metadata

    def get_player_ids(self) -> list[PlayerId]:
        return [PlayerId(p.player_id) for p in self.scenario.player_spawns]

    def get_player_name(self, player_id: PlayerId) -> str:
        for p in self.scenario.player_spawns:
            if p.player_id == int(player_id):
                return p.name
        return f"Player-{int(player_id)}"

    def round_assignment_trace(self) -> list[dict[str, Any]]:
        """round_assignment で player に割り当てた枠を、trace に載せる形で返す (#1514)。"""
        spawns = {p.string_id: p for p in self.scenario.player_spawns}
        return [
            {
                "player_id": int(spawns[a.player_string_id].player_id),
                "player_name": spawns[a.player_string_id].name,
                "group_index": a.group_index,
                "slot_index": a.slot_index,
                "spawn_spot": a.spawn_spot,
                "initial_state": dict(a.initial_state),
            }
            for a in self.scenario.round_assignments
        ]

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

    def _ensure_llm_failure_monitor(self) -> LlmFailureStreakMonitor:
        with self._llm_failure_monitor_lock:
            if self._llm_failure_monitor is None:
                # 設定を持たない runtime (presentation 単体テスト等) は既定で
                # 動かす。**設定はあるのに属性が無い場合は落とす** — 属性名の
                # 改名や別 DTO の混入で、`LLM_FAILURE_STREAK_ABORT=0` にした
                # つもりの run が黙って閾値 8 で止まるのを防ぐ。
                if self._runtime_config is None:
                    threshold = DEFAULT_FAILURE_STREAK_ABORT
                else:
                    threshold = int(self._runtime_config.llm_failure_streak_abort)
                self._llm_failure_monitor = LlmFailureStreakMonitor(
                    threshold=threshold
                )
            return self._llm_failure_monitor

    def record_llm_outcome(
        self,
        *,
        success: bool,
        error_code: str = "",
        tick: int | None = None,
    ) -> None:
        """LLM 呼び出し 1 件の結末を、連続失敗の監視へ渡す。

        `LlmMetricsTraceSink.record` から呼ばれる。trace を読み直さずに
        判定できることが要件で、run 中に trace.jsonl を舐める形にすると
        tick ごとにファイル全体を読むことになる。
        """
        self._ensure_llm_failure_monitor().record(
            success=success, error_code=error_code, tick=tick
        )

    def llm_abort_reason(self) -> str | None:
        """恒久障害とみなせるなら停止理由を返す。健全なら None。

        判定は**サーバが名乗る理由ではなく、retry を尽くしたあとの
        「治らなさ」**で行う。理由による分類は
        `litellm_client._is_retryable_transient_error` の担当。
        """
        monitor = self._ensure_llm_failure_monitor()
        if not monitor.is_tripped():
            return None
        return monitor.describe()

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
        if self._public_sns_command_service is not None:
            try:
                self._public_sns_command_service.retry_pending_notifications(limit=100)
            except Exception as exc:
                self._record_world_tick_follow_up_failure(
                    exc, stage="public_sns.retry_notifications", target_kind="stage"
                )
        return tick.value

    def _record_world_tick_follow_up_failure(
        self,
        exc: Exception,
        *,
        stage: str,
        target_kind: str,
        target_id: object = None,
        player_id: int | None = None,
    ) -> None:
        """確定済みの処理に続く後処理の失敗を trace に残す (design_decisions D1558)。"""
        from ai_rpg_world.application.world_graph.world_tick_failure_isolation import (
            WorldTickFailureIsolator,
        )
        from ai_rpg_world.domain.common.value_object import WorldTick

        isolator = self._world_tick_failure_isolator or WorldTickFailureIsolator.fail_fast()
        isolator.record_continued_failure(
            exc,
            stage=stage,
            tick=WorldTick(self.current_tick()),
            target_kind=target_kind,
            target_id=target_id,
            player_id=player_id,
        )

    def _record_committed_player_travel_tick(self, player_id: PlayerId) -> None:
        """確定済みの player 移動 1 tick を実験指標へ反映する。"""
        player_id_value = int(player_id)
        self._cumulative_travel_ticks_by_player[player_id_value] = (
            self._cumulative_travel_ticks_by_player.get(player_id_value, 0) + 1
        )

    def _report_travel_blocked(
        self, player_id: PlayerId, blocked: SpotTravelBlocked
    ) -> None:
        """区間が閉じて移動を取りやめたことを、本人の観測・trace・行動履歴に残す。

        到着の行が無いと本人が移動中だと思い込むのと同じで (到着の履歴の
        hook を参照)、出発の行だけが残ると取りやめたことに気づけない。
        観測は手番を積むためにも要る。止まった本人は到着の観察者を通らない。
        観測を最初に出し、trace の記録の失敗は個別に握る。trace の失敗で
        本人への観測と手番まで失うと、止まったことを知らないまま手番も来ない。
        """
        cue = travel_blocked_cue(blocked)
        self._emit_observation_directly(
            player_id,
            ObservationOutput(
                prose=cue,
                structured={
                    "type": "travel_blocked",
                    "connection_name": blocked.connection_name,
                    "message": cue,
                },
                observation_category="self_only",
                schedules_turn=True,
                breaks_movement=False,
            ),
        )
        graph = self._spot_graph_repo.find_graph()
        from_name = graph.get_spot(blocked.from_spot_id).name
        to_name = graph.get_spot(blocked.to_spot_id).name
        destination_name = graph.get_spot(blocked.destination_spot_id).name
        recorder = self._trace_recorder
        if recorder is not None:
            from ai_rpg_world.application.trace import TraceEventKind

            try:
                recorder.record(
                    TraceEventKind.TRAVEL_BLOCKED,
                    tick=self.current_tick(),
                    player_id=int(player_id),
                    connection_id=blocked.connection_id.value,
                    connection_name=blocked.connection_name,
                    passage_kind=blocked.passage_kind,
                    passage_state=blocked.passage_state,
                    reason=blocked.reason.value,
                    condition_message=blocked.condition_message,
                    from_spot_id=blocked.from_spot_id.value,
                    from_spot_name=from_name,
                    to_spot_id=blocked.to_spot_id.value,
                    to_spot_name=to_name,
                    destination_spot_id=blocked.destination_spot_id.value,
                    destination_spot_name=destination_name,
                )
            except Exception:
                logger.exception(
                    "TRAVEL_BLOCKED trace record failed: player=%s connection=%s",
                    int(player_id),
                    blocked.connection_id.value,
                )
        self._record_action_result(
            player_id,
            f"{blocked.connection_name}の先へ進めず、「{destination_name}」への移動を取りやめた",
            f"「{from_name}」にとどまっている。ここから次の行動を選べる。",
            tool_name=TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
            success=False,
            error_code="TRAVEL_BLOCKED",
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
        外側から trace を有効化する用途。
        """
        self._trace_recorder = recorder
        # 市場の値動きは trace が一次データになる。recorder が差し込まれた
        # 時点で市場へも渡さないと、**run 後に価格の時系列が引けない**。
        market_service = getattr(self, "_market_service", None)
        if market_service is not None:
            market_service.set_trace_recorder(recorder, self.current_tick)
        player_interaction_service = getattr(self, "_player_interaction_service", None)
        if player_interaction_service is not None:
            player_interaction_service.set_trace_recorder(recorder, self.current_tick)
        # 短期記憶の構築時点では recorder が未確定なので、L4 と圧縮発火の
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

    @property
    def world_tick_failure_isolator(self) -> WorldTickFailureIsolator | None:
        return self._world_tick_failure_isolator

    def world_tick_failure_counts(self) -> dict[str, int]:
        """世界の tick で取りやめた (fail_fast なら止めた) 1 体ぶんの処理の件数を段ごとに返す。"""
        if self._world_tick_failure_isolator is None:
            return {}
        return self._world_tick_failure_isolator.failure_counts()

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
        self._cached_default_prompt_builder: Any | None = None

    def set_simulation_llm_turn_trigger(
        self, trigger: ILlmTurnTrigger | None
    ) -> None:
        """ティック後の :meth:`ILlmTurnTrigger.run_scheduled_turns` に使う実装を差し替える。

        プレゼン層の ``_WorldLlmWiring`` など、実際に LLM を起動するトリガに
        切り替える。単体デモの既定は :class:`WorldStandaloneNoopLlmTurnTrigger`。
        """
        self._simulation_service.set_llm_turn_trigger(trigger)

    def set_simulation_heartbeat_emitter(
        self, emitter: HeartbeatObservationEmitter | None
    ) -> None:
        """ティック後の heartbeat emitter を注入する（未設定なら送信しない）。

        ``SpotGraphSimulationApplicationService`` の post-tick フックに委譲する。
        """
        self._simulation_service.set_heartbeat_emitter(emitter)

    def set_observation_turn_scheduler(
        self, scheduler: ObservationTurnScheduler | None
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
        target_player_id: PlayerId | None = None,
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
        violations: tuple[PromptArgumentContractViolation, ...],
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
                episode_recall_max_handles=1,
                episode_index_revision_enabled=True,
            )
        )
        definitions.append(
            assess_situation_definition()
        )
        missing = unclassified_action_argument_names(definitions)
        if missing:
            raise ActionArgumentClassificationError(
                "行動履歴での扱いが未分類の tool 引数があります: "
                + ", ".join(missing)
            )

    def _compute_task_progress_line(self) -> str | None:
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
        parts: list[str] = []
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

    def _compute_meeting_status_line(self, player_id: PlayerId) -> str | None:
        """会議中なら、``player_id`` から見た状況を 1 行にまとめて返す。自由時間なら None。

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
        #
        # 促すのは vote を実際に出す相手だけ。投票済みの人や死者にも促して
        # いた run では、促しに従って vote を選び TOOL_NOT_OFFERED_NOW で
        # 手番を捨てていた。
        _, phase_tools = self._split_spot_tool_names_for(
            ("vote",), player_id=player_id, in_meeting=True
        )
        if "vote" not in phase_tools:
            if self._game_phase_store.has_voted(player_id):
                parts.append("自分はもう投票した。あとは結果を待つ")
            else:
                parts.append("自分は投票できない。あとは結果を待つ")
        elif remaining <= _MEETING_URGENT_REMAINING_TICKS:
            parts.append("いま投票しないと、誰も追放されないまま終わる")
        else:
            parts.append("投票しないまま打ち切られると、誰も追放されない")
        return "。".join(parts) + "。"

    def _meeting_initiator_display_name(self) -> str | None:
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

    def _compute_tick_budget_remaining(self) -> int | None:
        """シナリオの lose_conditions に TICK_LIMIT があれば残り tick を返す。

        WIN 条件には触れず「時間切れまでの猶予」だけ LLM に伝えるためのメタ情報。
        複数の TICK_LIMIT 条件があるときは最小値 (一番早く切れるもの) を採用。
        """
        from ai_rpg_world.domain.world_graph.enum.game_end_condition_type import (
            GameEndConditionTypeEnum,
        )
        limits: list[int] = []
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
            minutes_per_tick=_minutes_per_tick(self.scenario),
            meeting_status_line=self._compute_meeting_status_line(player_id),
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
        self, definitions: list[ToolDefinitionDto]
    ) -> list[ToolDefinitionDto]:
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

    def _validate_disabled_tool_names(self) -> tuple[str, ...]:
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
        known = {defn.name for defn, _ in get_spot_graph_specs()} | {d.name for d in get_public_sns_definitions()}
        unknown = [name for name in disabled if name not in known]
        if unknown:
            raise ToolExposureConfigurationError(
                "disabled_tools に実在しないツール名があります: "
                f"{', '.join(unknown)} / 指定できるのは: {', '.join(sorted(known))}"
            )
        return tuple(disabled)

    def get_tool_definitions(
        self,
        *,
        tool_schema_mode: str = "legacy",
        as_meeting_phase: bool | None = None,
        player_id: PlayerId | None = None,
        for_every_player: bool = False,
    ) -> list[ToolDefinitionDto]:
        """LLM に渡されるツール定義（OpenAI tools 形式）を返す。

        ツール露出の強制点はこのメソッドに集約する。シナリオ由来の
        ツール露出 (会議・商人・市場の宣言) と、設定由来の記憶系ツール露出を同じ
        場所で決めることで、「なぜ tool が LLM に出ないか」の追跡点を分散させない。

        記憶系ツールは、該当 runtime config が true かつ実行器が組めた場合だけ
        露出する。config true なのに前提配線が無い場合は fail-fast する。
        比較実験で「有効にしたつもりが黙って無効」になる静かな失敗を避けるため。

        ``tool_schema_mode="legacy"`` は従来互換。``"reason_first"`` では
        ``assess_situation`` を加え、行動 tool から step1 所有の
        ``inner_thought`` だけを外す。

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
        common_names, phase_names = self._split_spot_tool_names_for(
            by_name.keys(), player_id=player_id, in_meeting=in_meeting
        )
        common_spot = [by_name[n] for n in common_names]
        phase_spot = [by_name[n] for n in phase_names]
        assessment = (
            [
                assess_situation_definition()
            ]
            if tool_schema_mode == "reason_first"
            else []
        )
        definitions = (
            common_spot + phase_spot + self._build_memory_tool_definitions()
        )
        by_name = {definition.name: definition for definition in definitions}
        ordered_names = self.tool_exposure.order_for_payload(by_name.keys())
        return [by_name[name] for name in ordered_names] + assessment

    def _split_spot_tool_names_for(
        self,
        names: Iterable[str],
        *,
        player_id: PlayerId | None,
        in_meeting: bool,
    ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """本人の状態を ``split_for_phase`` に渡す。

        ツール定義と本文 (会議の状況行) の両方がここを通る。本文だけが別の
        条件で書き分けると、投票済みの人に「いま投票しないと」と勧めながら
        vote を出さない形になる。
        """
        return self.tool_exposure.split_for_phase(
            names,
            in_meeting=in_meeting,
            voting_completed=(
                player_id is not None
                and in_meeting
                and self._game_phase_store.has_voted(player_id)
            ),
            departed=(
                player_id is not None
                and self._player_perception_policy.is_departed(player_id)
            ),
        )

    def _build_spot_tool_definitions(
        self, tool_schema_mode: str
    ) -> list[ToolDefinitionDto]:
        """この世界に在る spot tool を、フェーズを問わずすべて返す。

        並べ替えとフェーズの出し分けは呼び出し側。ここは「在るか無いか」
        だけを決める。
        """
        spot = [
            self._with_being_memo_if_enabled(defn)
            for defn in [*(d for d, _ in get_spot_graph_specs()), *get_public_sns_definitions()]
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

    def _build_memory_tool_definitions(self) -> list[ToolDefinitionDto]:
        """記憶系ツール (episode_recall / episode_revise_index) を返す。

        世界ではなく記憶の部品で決まるので `ToolExposure` には置かない。
        create_world_runtime で組んだ runtime には常に出す (#1631)。

        実行器が組めていなければ fail-fast する。黙って出さないと、
        常に出すはずの道具が run から消えたことに気づけない。
        """
        cfg = self._runtime_config
        episode_index_revision_enabled = self._episode_index_enabled()
        episode_recall_max_handles = None
        if episode_index_revision_enabled:
            if (
                self._being_episode_recall_tool_executor is None
                or self._being_episode_index_revision_tool_executor is None
            ):
                raise ToolExposureConfigurationError(
                    f"{TOOL_NAME_EPISODE_RECALL} and {TOOL_NAME_EPISODE_REVISE_INDEX} are "
                    "always offered (#1631), but their executors are not wired; build the "
                    "runtime with create_world_runtime"
                )
            assert cfg is not None
            episode_recall_max_handles = cfg.being_episode_recall_max_handles
        return [
            defn
            for defn, _ in get_memory_specs(
                episode_recall_max_handles=episode_recall_max_handles,
                episode_index_revision_enabled=episode_index_revision_enabled,
            )
        ]

    def _episode_index_parts_named_in_system_prompt(self) -> tuple[bool, bool]:
        """システムプロンプトが指してよい (【思い出せる出来事】, ``episode_recall``) を返す (#1623)。

        ツールは #1616 と同じく、実際に出すツールの一覧から決める。
        """
        offered = {
            definition.name
            for definition in self.get_tool_definitions(for_every_player=True)
        }
        return self._episode_index_enabled(), TOOL_NAME_EPISODE_RECALL in offered

    def _episode_index_enabled(self) -> bool:
        # create_world_runtime で組んだ runtime には、目次と書き起こしが常に入る (#1631)。
        return self._runtime_config is not None

    def episode_index_text(self, player_id: PlayerId) -> str:
        """【思い出せる出来事】の本体。出すたびに、出した呼び名を trace に残す (#1623)。

        本人の Being が引けなければ空文字で、欄を出さない。
        """
        from ai_rpg_world.application.observation.being_contract import (
            environment_entry_for_player,
        )
        from ai_rpg_world.being.application.episode_index_text import (
            format_episode_index,
        )
        from ai_rpg_world.being.domain.episode_index_selection import (
            RecalledRisesToTop,
        )

        acting = self._acting_being_for(player_id)
        if acting is None:
            return ""
        cfg = self._runtime_config
        assert cfg is not None
        selection = RecalledRisesToTop()
        episodes = self._being_episode_store.list_by_being(acting.being_id)
        shown = selection.select(episodes, limit=cfg.being_episode_index_limit)
        try:
            self._trace_recorder.record(
                TraceEventKind.EPISODE_INDEX_SHOWN,
                tick=self.current_tick(),
                player_id=int(player_id.value),
                being_id=acting.being_id.value,
                order="recalled_rises_to_top",
                limit=cfg.being_episode_index_limit,
                total_count=len(episodes),
                shown_handles=[e.handle for e in shown],
            )
        except Exception:
            logger.exception("trace recorder.record raised for EPISODE_INDEX_SHOWN; skipping")
        return format_episode_index(
            shown,
            current_environment_name=environment_entry_for_player(
                self.scenario, player_id
            ).environment_name,
        )

    def _being_memo_enabled(self) -> bool:
        # create_world_runtime で組んだ runtime には、メモ帳が常に入る (#1631)。
        return self._runtime_config is not None

    def memo_episode_source_offered(self) -> bool:
        """メモの出どころにエピソードの呼び名を選ばせるか (#1628)。

        本人が呼び名を知るのは【思い出せる出来事】からなので、目次を出す設定でだけ選ばせる (#1623)。
        """
        return self._episode_index_enabled()

    def _with_being_memo_if_enabled(
        self, definition: ToolDefinitionDto
    ) -> ToolDefinitionDto:
        """メモ帳が有効なら、環境の tool に ``memo`` を足す (#1628)。

        付ける範囲は予期の引数と同じで、記憶の tool と ``assess_situation`` には付けない。
        run 全体で同じ定義を出すので、ターンをまたいで変わらない。
        """
        if not self._being_memo_enabled():
            return definition
        return with_memo_schema(
            definition, episode_source_offered=self.memo_episode_source_offered()
        )

    def being_memo_text(self, player_id: PlayerId) -> str:
        """【メモ】の本体。本人の Being が引けなければ空文字で、欄を出さない。"""
        from ai_rpg_world.being.application.memo_book_text import format_memo_book

        acting = self._acting_being_for(player_id)
        if acting is None:
            return ""
        return format_memo_book(
            self._being_memo_store.get(acting.being_id),
            current_environment_name=self.environment_name_for(player_id),
        )

    def environment_name_for(self, player_id: PlayerId) -> str:
        from ai_rpg_world.application.observation.being_contract import (
            environment_entry_for_player,
        )

        return environment_entry_for_player(self.scenario, player_id).environment_name

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
        # 経路の naive と混ざると時刻の比較で TypeError になる。
        if not appender.append(
            player_id, output, datetime.now(timezone.utc), self._time_label()
        ):
            return
        scheduler = self._observation_turn_scheduler
        if scheduler is not None:
            scheduler.maybe_schedule(player_id, output)

    def _record_action_result(
        self,
        player_id: PlayerId,
        action_summary: str,
        result_summary: str,
        *,
        tool_name: str,
        identifier_arguments: Mapping[str, str] | None = None,
        free_text_argument_names: tuple[str, ...] = (),
        success: bool = True,
        error_code: str | None = None,
        inner_thought: str | None = None,
    ) -> None:
        """action_result_store に 1 件積む。

        ``tool_name`` は必須引数: 第20回実験で「episode_cues に常に
        ``action:unknown_tool`` が立つ」問題が観測されたため、呼び出し側で
        必ず LLM tool 名 (例: ``TOOL_NAME_SPOT_GRAPH_TRAVEL_TO``) を明示する。
        ``success`` / ``error_code`` も同様に「常に ``outcome:success`` が立つ」
        ノイズの原因なので、失敗を検知できる経路は明示的に渡す。

        ``inner_thought``: LLM が行動前に書いた独白。do_* 経由で raw args 由来の
        値が渡る (U2)。
        """
        # U1 (#526 後続): store への append を共有 ActionResultRecorder に委譲する。
        # tz-aware UTC で統一 (詳細は _emit_observation_directly のコメント参照)。
        recorder = ActionResultRecorder(self._action_result_store)
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
            inner_thought=inner_thought,
            occurred_tick=self.current_tick(),
            # 描画時刻から相対ラベルを再計算せず、記録時の世界時刻を固定する。
            game_time_label=self._time_label(),
        )

    def _wire_being_stack(self) -> None:
        """プレイヤーに結びつく Being の保存先・用意・解決を、まだ無ければ組む。

        記憶の部品はどれも Being を単位に持つ (#1631)。
        """
        if hasattr(self, "_aux_being_repository"):
            return
        from ai_rpg_world.application.being.being_attachment_resolver import (
            BeingAttachmentResolver,
        )
        from ai_rpg_world.application.being.being_provisioning_service import (
            BeingProvisioningService,
        )
        from ai_rpg_world.domain.world.value_object.world_id import (
            DEFAULT_SINGLE_WORLD_ID,
        )
        from ai_rpg_world.infrastructure.repository.in_memory_being_repository import (
            InMemoryBeingRepository,
        )

        self._aux_being_repository = InMemoryBeingRepository()
        self._aux_being_provisioning = BeingProvisioningService(
            self._aux_being_repository
        )
        self._aux_being_resolver = BeingAttachmentResolver(self._aux_being_repository)
        self._aux_being_default_world_id = DEFAULT_SINGLE_WORLD_ID

    @property
    def aux_being_resolver(self) -> Any:
        """``_aux_being_resolver`` の公開。``_wire_being_stack`` を呼んでいないと None。"""
        return getattr(self, "_aux_being_resolver", None)

    @property
    def aux_being_default_world_id(self) -> Any:
        """Phase 3 Step 3a-3: aux Being の default WorldId 公開アクセサ。"""
        return getattr(self, "_aux_being_default_world_id", None)

    def advance_memory_turn(self, player_id: PlayerId) -> int | None:
        """エージェントの 1 手を受け取ったときに、Being のターン数を 1 進める (#1440)。

        Being に結びつかないプレイヤーなら進めずに None を返す。
        """
        acting = self._acting_being_for(player_id)
        if acting is None:
            return None
        return self._memory_turn_clock.advance_turn(acting.being_id)

    def _write_compacted_episodes(
        self, player_id: PlayerId, entries: Sequence[Any]
    ) -> None:
        from ai_rpg_world.application.being.player_episode_writing import (
            TRIGGER_COMPACTION,
        )

        if self._player_episode_writing is None:
            raise RuntimeError("episode writing is not wired; build the runtime with create_world_runtime")
        self._player_episode_writing.write(player_id, entries, trigger=TRIGGER_COMPACTION)

    def write_episodes_on_leaving(self, *, skip_reason: str | None = None) -> None:
        """環境を離れるとき (run の終わり) に、まだ畳まれていない出来事からエピソードを書く (#1626)。

        書き起こしを有効にしていなければ何もしない。``skip_reason`` を渡すと書かずに、
        プレイヤーごとにその理由を trace に残す。
        """
        if self._player_episode_writing is None:
            return
        from ai_rpg_world.application.being.player_episode_writing import TRIGGER_LEAVING
        from ai_rpg_world.application.llm.services.summarizing_short_term_memory import (
            SummarizingShortTermMemory,
        )

        memory = self._short_term_memory
        if not isinstance(memory, SummarizingShortTermMemory):
            raise RuntimeError("episode writing needs SummarizingShortTermMemory")
        for player_id in self.get_player_ids():
            if skip_reason is not None:
                self._player_episode_writing.skip(
                    player_id, trigger=TRIGGER_LEAVING, reason=skip_reason
                )
                continue
            self._player_episode_writing.write(
                player_id,
                memory.uncompacted_entries(player_id),
                trigger=TRIGGER_LEAVING,
            )

    def _acting_being_for(self, player_id: PlayerId) -> ActingBeing | None:
        self._wire_being_stack()
        self._aux_being_provisioning.ensure_attached(player_id)
        being_id = self._aux_being_resolver.resolve_being_id(
            self._aux_being_default_world_id, player_id
        )
        if being_id is None:
            return None
        return ActingBeing(player_id=player_id, being_id=being_id)

    def run_llm_auxiliary_tool(
        self, player_id: PlayerId, name: str, arguments: dict[str, Any]
    ) -> LlmCommandResultDto:
        """エピソードの道具を実行する。

        handler を起動する前に player_id に Being が attach されていることを保証する。
        """
        acting = self._acting_being_for(player_id)
        if acting is None:
            return LlmCommandResultDto(
                success=False,
                message="Being is not attached to this player.",
                error_code="INVALID_STATE",
            )
        handlers: dict[str, Any] = {}

        def _merge_handlers(next_handlers: dict[str, Any]) -> None:
            # サイレント上書き防止: 将来 executor が増えたとき同名 tool が
            # 出ると後勝ちで挙動が変わるため、明示的に衝突を検出する。
            overlap = handlers.keys() & next_handlers.keys()
            if overlap:
                raise RuntimeError(
                    f"tool handler name collision in aux stack: {sorted(overlap)}"
                )
            handlers.update(next_handlers)

        if self._being_episode_recall_tool_executor is not None:
            _merge_handlers(self._being_episode_recall_tool_executor.get_handlers())
        if self._being_episode_index_revision_tool_executor is not None:
            _merge_handlers(self._being_episode_index_revision_tool_executor.get_handlers())
        handler = handlers.get(name)
        if handler is None:
            return LlmCommandResultDto(
                success=False,
                message=f"未対応のツールです: {name}",
                error_code="UNSUPPORTED_TOOL",
            )
        return cast(LlmCommandResultDto, handler(acting, arguments))

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

    def _players_missing_objective(self) -> list[str]:
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

    # Issue #227 後続 HIGH-3 改善: stateless formatter / strategy を class-level
    # に持ち、build_full_prompt の毎回 new を避ける + 本家 DefaultPromptBuilder と
    # 同じインスタンスタイプを使うことを明示する。
    _recent_events_formatter: ClassVar[DefaultRecentEventsFormatter] = (
        DefaultRecentEventsFormatter()
    )
    _context_strategy: SectionBasedContextFormatStrategy = field(
        default_factory=SectionBasedContextFormatStrategy
    )

    def _get_or_build_default_prompt_builder(self) -> DefaultPromptBuilder:
        """本家 DefaultPromptBuilder のインスタンスを lazy 構築してキャッシュする。

        Issue #227 後続 HIGH-3 Part 2: world_runtime の prompt 組み立てを
        DefaultPromptBuilder に統合するため、必要な adapter を集めて 1 回だけ
        構築する。
        """
        cached = getattr(self, "_cached_default_prompt_builder", None)
        if cached is not None:
            return cast("DefaultPromptBuilder", cached)

        from ai_rpg_world.application.llm.services.prompt_builder import (
            DefaultPromptBuilder,
        )
        from ai_rpg_world.application.llm.services.prompt_builder_config import (
            PromptBuilderCoreServices,
            PromptLimits,
            PromptSectionProviders,
        )
        from ai_rpg_world.application.world_runtime.default_prompt_builder_adapters import (
            WorldAvailableToolsProvider,
            WorldProfileRepositoryAdapter,
            WorldRuntimeQueryAdapter,
            WorldSystemPromptBuilder,
        )

        core = PromptBuilderCoreServices(
            observation_buffer=self._obs_buffer,
            short_term_memory=self._short_term_memory,
            recent_event_store=self._recent_event_store,
            world_query_service=WorldRuntimeQueryAdapter(self),
            player_profile_repository=WorldProfileRepositoryAdapter(self),
            current_state_formatter=self._formatter,
            recent_events_formatter=self._recent_events_formatter,
            context_format_strategy=self._context_strategy,
            system_prompt_builder=WorldSystemPromptBuilder(self),
            available_tools_provider=WorldAvailableToolsProvider(),
            recent_events_projection=(self._public_sns_projection.project if self._public_sns_projection else None),
        )
        # objective_text は scenario.metadata.llm_objective_text を 1 度だけ解決する。
        # 空のとき ValueError が立つので、prompt builder 構築時点で fail-fast。
        # lambda 内で resolve すると毎ターン呼ばれて重複ログ + 同一例外を投げる
        # ことになるため、ここで closure キャプチャする。
        resolved_objective_text = self._resolve_scenario_llm_objective_text()
        sections = PromptSectionProviders(
            # 目的層 G6: players[].objective があればその人だけ別の目的文に
            # なり、無ければシナリオ共通文になる。
            objective_text_provider=lambda pid: self._resolve_player_objective_text(
                pid, resolved_objective_text
            ),
            being_memo_text_provider=(
                self.being_memo_text if self._being_memo_enabled() else None
            ),
            known_people_text_provider=(
                self._player_acquaintances.known_people_text
                if self._player_acquaintances is not None
                else None
            ),
            episode_index_text_provider=(
                self.episode_index_text if self._episode_index_enabled() else None
            ),
        )
        limits = PromptLimits(
            tile_map_enabled=False,
            default_action_instruction=self._ESCAPE_GAME_ACTION_INSTRUCTION,
        )
        builder = DefaultPromptBuilder(
            core,
            sections=sections,
            limits=limits,
            ui_context_builder=self._ui_context_builder,
            current_tick_provider=lambda: self.current_tick(),
            # trace_recorder は provider 経由で渡す (set_trace_recorder で後から差し込まれる)。
            trace_recorder_provider=lambda: self._trace_recorder,
            # presentation 層で先に組まれている loop_guard (record_and_check の
            # 呼び出し主) を peek_streak 用にも共有する。``None`` のままなら
            # instruction 末尾の警告 prefix は出ない。
            tool_call_loop_guard=getattr(
                self, "_injected_tool_call_loop_guard", None
            ),
        )
        self._cached_default_prompt_builder = builder
        return builder

    def build_full_prompt(
        self,
        player_id: PlayerId,
        *,
        action_instruction: str | None = None,
    ) -> dict[str, Any]:
        """各プレイヤーが LLM ターンで実際に受け取る完全なプロンプトを構築する。

        Issue #227 後続 HIGH-3 Part 2: 本家 DefaultPromptBuilder.build() に統合した。
        section 組み立て・recent_events・tile-map field 制御は
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
        self._wire_being_stack()
        if self._public_sns_command_service is not None:
            try:
                self._public_sns_command_service.retry_pending_notifications(limit=100)
            except Exception:
                logger.exception("公開SNSの通知再送が未完了です")
        # observation buffer の drain は DefaultPromptBuilder.build() 内で行われる

        tail_sections = tuple(
            section
            for section in (
                self._public_sns_screen_text(player_id),
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
            "action_instruction": result["action_instruction"],
            "sns_shown_notification_ids": result.get("sns_shown_notification_ids", ()),
            "sns_screen_generation": getattr(self._public_sns_screens.get(int(player_id)), "generation", None),
        }

    def _public_sns_header_text(self, player_id: PlayerId) -> str:
        store = self._public_sns_data_store
        if store is None:
            return ""
        from ai_rpg_world.domain.sns.value_object.user_id import UserId
        user = store.sns_users.get(UserId(int(player_id)))
        if user is None:
            return ""
        own_id = f"sns:{store.sns_public_namespace}:user:{user.identity_token}"
        pending = self._public_sns_projection.pending_count(int(player_id))
        return f"【公開SNS】自分: {user.profile.display_name} / 人物: {own_id}\n未表示通知: {pending}件。受信箱で確認できます。"

    def _public_sns_screen_text(self, player_id: PlayerId) -> str:
        header = self._public_sns_header_text(player_id)
        if not header:
            return ""
        screen = self._public_sns_screens.get(int(player_id))
        status = self._public_sns_screens.presentation_status(int(player_id))
        return header + "\n" + status + ("\n" + screen.text if screen else "")

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
        interaction_parameters: dict[str, Any] | None = None,
        identifier_arguments: Mapping[str, str] | None = None,
        free_text_argument_names: tuple[str, ...] = (),
        inner_thought: str | None = None,
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
        )
        return result

    def do_interact_with_item(
        self,
        player_id: PlayerId,
        item_spec_id: ItemSpecId,
        action_name: str,
        *,
        interaction_parameters: dict[str, Any] | None = None,
        identifier_arguments: Mapping[str, str] | None = None,
        free_text_argument_names: tuple[str, ...] = (),
        inner_thought: str | None = None,
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
        )
        return result

    # ── フェーズ遷移 (会議と投票) ──

    def eligible_voters(self) -> list[PlayerId]:
        """投票できる player。行動可能な生存者だけ。

        退場した相手 (DEAD / EJECTED) と倒れている相手を外す。倒れている
        相手は観測が届かないので投票する機会が無く、母数に残すと**永久に
        待つ**ことになる。過半数の計算も狂い、「誰も追放できない」が
        「同点で追放なし」と区別できなくなる (設計 doc H-1)。
        """
        voters: list[PlayerId] = []
        for pid in self.get_player_ids():
            if not self._player_life_query.can_vote(pid):
                continue
            voters.append(pid)
        return voters

    def cast_vote(self, voter_player_id: PlayerId, target_player_id: Any=None) -> Any:
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

        集計と投票そのものは PR 6。ここは確定させる手段だけを用意する
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
    ) -> Any:
        """専用の会議commandへ緊急招集を委譲する。"""
        service = self._meeting_command_service
        if service is None:
            raise RuntimeError("MeetingCommandService is not wired")
        return service.call_emergency_meeting(player_id, trigger=trigger)

    def report_body(self, reporter_player_id: PlayerId, target_player_id: PlayerId) -> Any:
        """専用の会議commandへ死体報告を委譲する。"""
        service = self._meeting_command_service
        if service is None:
            raise RuntimeError("MeetingCommandService is not wired")
        return service.report_body(reporter_player_id, target_player_id)

    def begin_meeting(
        self,
        *,
        initiator_player_id: PlayerId | None = None,
        trigger: str = MeetingStartTrigger.EMERGENCY_BUTTON.value,
    ) -> Any:
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

    def end_meeting(self, *, reason: str = MeetingEndReason.VOTE_CONCLUDED.value) -> Any:
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

    def _meeting_location(self, state: Any) -> tuple[str | None, str | None]:
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
        initiator_player_id: PlayerId | None,
        after_apply: Callable[[], None] | None = None,
    ) -> Any:
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

    def available_player_action_names(self, actor_player_id: PlayerId) -> tuple[str, ...]:
        """**その人に見えている**対人 action 名 (シナリオ直下 ``player_interactions``)。

        行為者を必ず受け取る。以前は引数が無く全件を返しており、クルーが
        操作名を打ち間違えると ``strike_down`` の存在が案内から漏れていた。
        """
        svc = getattr(self, "_player_interaction_service", None)
        if svc is None:
            return ()
        status = self._player_status_repo.find_by_id(actor_player_id)
        return cast(
            "tuple[str, ...]",
            svc.available_action_names(
                getattr(status, "state", None),
                actor_player_id=actor_player_id,
            ),
        )

    def set_target_item_name_rescue(self, rescue: Any | None) -> None:
        """人を対象にした操作で、品名を相手の所持品から意味で読み替える判断を注入する (D1641)。"""
        self._player_interaction_service.set_item_name_rescue(rescue)

    @property
    def target_item_name_rescue(self) -> Any | None:
        return self._player_interaction_service.item_name_rescue

    def do_interact_with_player(
        self, actor_player_id: PlayerId, target_player_id: PlayerId, action_name: str,
        *,
        interaction_parameters: dict[str, Any] | None = None,
        identifier_arguments: Mapping[str, str] | None = None,
        free_text_argument_names: tuple[str, ...] = (),
        inner_thought: str | None = None,
    ) -> Any:
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

    def list_ground_items_at_player_spot(self, player_id: PlayerId) -> tuple[Any, ...]:
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
        identifier_arguments: Mapping[str, str] | None = None,
        free_text_argument_names: tuple[str, ...] = (),
        inner_thought: str | None = None,
    ) -> SpotExplorationResultDto:
        spot_name = self.get_player_spot_name(player_id)
        result = self._exploration_service.explore_once(player_id)
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
        )
        return result

    def do_move(
        self,
        player_id: PlayerId,
        dest_spot_str_id: str,
        *,
        identifier_arguments: Mapping[str, str] | None = None,
        free_text_argument_names: tuple[str, ...] = (),
        inner_thought: str | None = None,
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
        owned: frozenset[ItemSpecId] = frozenset()
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
            )
            return

        # 移動開始の action result を記録する。start_travel_to_spot が成功している以上
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
            inner_thought=inner_thought,
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

    def _scenario_event_recipients(self, event: ScenarioEventDef) -> list[PlayerId]:
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

    def _is_distant_cue_active(self, cue: Any) -> bool | None:
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
        return bool(obj.state.get(state_key) == getattr(source, "equals", None))

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
        delivery_skipped_reason: str | None,
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
        """cue 境界検出の skipped 理由を trace に残す。"""
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

    def _append_food_spoiled_batch_observation(
        self,
        spoiled: Any,
    ) -> None:
        """第24回実験 (#343) + #356 後続: 食料腐敗 観測を **日単位で集約**。

        旧 (#350 同 tick 集約):
            「野いちごが3つ腐った。」 (同 tick 内のみ aggregate)
            → 1 日に渡って 8 個が別 tick で腐ると 8 件の観測が走る

        新 (本 PR): 1 日を跨いで pending buffer に貯め、日境界
        または game-end の直前に **1 日分まとめて** flush する:
            「今日は野いちごが5個、椰子の実が2個腐った。」

        spoiled は Sequence[(ItemInstanceId, ItemSpecId, str)]。
        """
        if not spoiled:
            return
        # 当日分の buffer に積む。flush は day boundary で行う (下記参照)。
        # field 化済 (#375 後続レビュー対応): 遅延 hasattr 初期化を廃止。
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
        """「今日」の区切りを、エージェントが見ている時計の 1 日にそろえる (#1576)。"""
        cfg = self.scenario.day_night_config
        if cfg is None:
            return (24 * 60) // _FALLBACK_MINUTES_PER_TICK
        return cfg.cycle.ticks_per_day

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
        # 全員が行動不能なときの停止はシナリオ内の勝敗規則ではなく、実験を行動不能
        # 状態で回し続けないための外的停止。世界の判定が成立した tick では世界の
        # 終了理由を残すため、外的停止は世界の判定が続行のときだけ見る
        # (design_decisions 43)。終了理由の文字列は、設定で切り替えていた頃の
        # run と同じ grep で拾えるように変えない。
        world_end = self._check_game_end_collective_mode()
        if world_end.is_ended:
            return world_end
        registry = self._player_outcome_registry
        if registry is not None and self._all_players_unable_to_act(registry):
            return GameEndResult(
                is_ended=True,
                result=None,
                reason=(
                    "外的停止 END_ON_ALL_DOWN: 行動可能プレイヤーがいない "
                    "(全員 down または outcome 確定済み)"
                ),
                player_outcomes=registry.snapshot(),
                team_results=(
                    self._decide_team_results() if self.scenario.teams else None
                ),
            )
        return world_end

    def _decide_team_results(self) -> Mapping[str, GameResultEnum]:
        """いまの世界で各チームの勝利条件を評価し、チームの勝敗を決める。"""
        satisfied, _ = self._satisfied_teams()
        return decide_team_results(self.scenario.teams, satisfied)

    def _satisfied_teams(self) -> tuple[frozenset[str], Mapping[str, str]]:
        """勝利条件が成立したチームの id と、チームごとの判定の理由を返す。

        成立しなかったチームの理由は、最後に評価した条件の理由 (何が足りないか)。
        """
        graph = self._spot_graph_repo.find_graph()
        flags = self._world_flag_state.as_frozen_set()
        player_ids = self.get_player_ids()
        from ai_rpg_world.domain.common.value_object import WorldTick
        tick = WorldTick(self._tick)
        player_states = self._collect_player_states(player_ids)
        player_outcomes = self._collect_player_outcomes(player_ids)
        satisfied: list[str] = []
        reasons: dict[str, str] = {}
        for team in self.scenario.teams:
            for condition in team.win_conditions:
                result = self._game_end_evaluator.evaluate(
                    graph, condition, flags, player_ids, tick,
                    player_states=player_states,
                    player_outcomes=player_outcomes,
                    result_on_match=GameResultEnum.WIN,
                    team_member_ids=team.member_player_ids,
                )
                reasons[team.team_id] = result.reason
                if result.is_ended:
                    satisfied.append(team.team_id)
                    break
        return frozenset(satisfied), reasons

    def team_result_trace(
        self, end_result: GameEndResult
    ) -> dict[str, Any] | None:
        """終了時のチームの勝敗と個人の結果を、trace の team_result の payload にする。"""
        from ai_rpg_world.domain.player.enum.player_outcome_enum import (
            PlayerOutcomeEnum,
        )

        team_results = end_result.team_results
        if not end_result.is_ended or team_results is None:
            return None
        registry = self._player_outcome_registry
        _, team_reasons = self._satisfied_teams()
        team_of: dict[int, str] = {}
        teams_payload: list[dict[str, Any]] = []
        for team in self.scenario.teams:
            result = team_results[team.team_id]
            teams_payload.append({
                "team_id": team.team_id,
                "name": team.name,
                "result": result.value,
                "satisfied": result is not GameResultEnum.LOSE,
                "reason": team_reasons[team.team_id],
                "member_player_ids": [int(pid) for pid in team.member_player_ids],
                "member_player_string_ids": [
                    self.id_mapper.get_str("player", int(pid))
                    for pid in team.member_player_ids
                ],
            })
            for pid in team.member_player_ids:
                team_of[int(pid)] = team.team_id
        players_payload: list[dict[str, Any]] = []
        for pid in self.get_player_ids():
            team_id = team_of[int(pid)]
            outcome = (
                registry.get_outcome(pid)
                if registry is not None
                else PlayerOutcomeEnum.UNRESOLVED
            )
            players_payload.append({
                "player_id": int(pid),
                "player_string_id": self.id_mapper.get_str("player", int(pid)),
                "player_name": self.get_player_name(pid),
                "team_id": team_id,
                "outcome": outcome.value,
                "result": team_results[team_id].value,
            })
        return {
            "reason": end_result.reason,
            "teams": teams_payload,
            "players": players_payload,
        }

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
        if self.scenario.teams:
            # チームの win を end より先に見る。勝ちが決まった tick に end も
            # 成立していても、勝ったチームを負けにしない。
            satisfied, team_reasons = self._satisfied_teams()
            if satisfied:
                return GameEndResult(
                    is_ended=True,
                    result=None,
                    reason=" / ".join(
                        f"{team.name}: {team_reasons[team.team_id]}"
                        for team in self.scenario.teams
                        if team.team_id in satisfied
                    ),
                    player_outcomes=self._collect_player_outcomes(player_ids),
                    team_results=decide_team_results(self.scenario.teams, satisfied),
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
                if self.scenario.teams:
                    return replace(
                        result,
                        team_results=decide_team_results(
                            self.scenario.teams, frozenset()
                        ),
                    )
                return result
        return GameEndResult(is_ended=False, result=None, reason="ゲーム続行中")

    def _collect_player_states(self, player_ids: Any) -> dict[int, dict[str, Any]]:
        """陣営条件が役割を読むための state 表を作る。"""
        states: dict[int, dict[str, Any]] = {}
        for pid in player_ids:
            status = self._player_status_repo.find_by_id(pid)
            states[int(pid)] = dict(status.state) if status is not None else {}
        return states

    def _collect_player_outcomes(self, player_ids: Any) -> dict[int, Any]:
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

    def get_player_spot_id(self, player_id: PlayerId) -> str | None:
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


def _build_short_term_memory(
    cfg: ResolvedLlmRuntimeConfig,
    *,
    scenario: Any,
    world_character: CharacterPromptInput | None,
    persona_block: str,
    event_store: UnifiedRecentEventStore,
    aux_llm_call_sink: AuxLlmCallSink | None,
    on_compacted: Callable[[PlayerId, Sequence[Any]], None] | None = None,
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
      2. ``SummarizingShortTermMemory(summary_service=X, persona_resolver=Z)``
         を ctor 一発で組む
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
    from ai_rpg_world.application.llm.services.short_term_memory_summary_service import (
        ShortTermMemorySummaryService,
    )
    from ai_rpg_world.application.llm.services.summarizing_short_term_memory import (
        SummarizingShortTermMemory,
    )
    from ai_rpg_world.application.llm.wiring._llm_client_factory import (
        create_llm_client_from_config,
    )
    from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient

    summary_service = None
    persona_resolver = None
    if cfg.llm_client_kind == "litellm":
        try:
            client = create_llm_client_from_config(cfg, aux_call_sink=aux_llm_call_sink)
        except Exception:
            logger.exception("LLM client factory failed; short-term LLM services disabled")
            client = None
        if isinstance(client, LiteLLMClient):
            summary_service = ShortTermMemorySummaryService(client)
            persona_resolver = _build_persona_resolver(
                scenario=scenario,
                world_character=world_character,
                persona_block=persona_block,
            )
            logger.info(
                "short-term memory: LLM 経路を ctor 注入 (rolling_summary + LiteLLM)。"
                "L4 は LLM 圧縮で生成される。"
            )
        else:
            logger.info(
                "LLM_CLIENT=litellm が未取得。short-term memory は template fallback "
                "only で動作 (L4 の LLM 圧縮は無効)。"
            )

    return SummarizingShortTermMemory(
        summary_service=summary_service,
        persona_resolver=persona_resolver,
        event_store=event_store,
        turn_cap=cfg.short_term_memory_turn_cap,
        compact_turn_count=cfg.short_term_memory_turn_compact_count,
        on_compacted=on_compacted,
    )


def _build_persona_resolver(
    *,
    scenario: Any,
    world_character: CharacterPromptInput | None,
    persona_block: str,
) -> Callable[[int], tuple[str, str]]:
    """player_id -> (name, persona_block) を引ける callable を組む。

    旧 _wire_short_term_llm_services 内に inline されていたロジックを抽出。
    規則:
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


def _record_meetings_at_spawn(
    scenario: ScenarioLoadResult, acquaintances: PlayerAcquaintances
) -> None:
    """初期配置で同じ場所にいた相手とは、最初から顔を合わせている。

    人が入ってきた観測は配置のあとにしか出ないので、初期配置の同席はここで記録する。
    """
    spawns_by_spot: dict[int, list[PlayerSpawnConfig]] = {}
    for spawn in scenario.player_spawns:
        spawns_by_spot.setdefault(spawn.spawn_spot_id.value, []).append(spawn)
    for spawns in spawns_by_spot.values():
        for spawn in spawns:
            for other in spawns:
                if other is not spawn:
                    acquaintances.record_meeting(PlayerId(spawn.player_id), other.name)


def _build_player_episode_writing(
    cfg: ResolvedLlmRuntimeConfig,
    *,
    runtime: WorldRuntime,
    turn_reader: MemoryTurnReader,
    persona_of: Callable[[int], tuple[str, str]],
) -> Any:
    """#1626: 書き起こしの部品を組む。LiteLLM が組めなければ起動を止める。"""
    from ai_rpg_world.application.being.player_episode_writing import (
        PlayerEpisodeWriting,
    )
    from ai_rpg_world.application.llm.services.stub_episode_writing_completion import (
        StubEpisodeWritingCompletion,
    )
    from ai_rpg_world.application.llm.wiring._llm_client_factory import (
        create_llm_client_from_config,
    )
    from ai_rpg_world.application.observation.being_contract import (
        environment_entry_for_player,
    )
    from ai_rpg_world.being.application.episode_writing import (
        EpisodeWriter,
        EpisodeWritingCompletion,
    )

    completion: EpisodeWritingCompletion
    if cfg.llm_client_kind == "litellm":
        client = create_llm_client_from_config(
            cfg, aux_call_sink=runtime._aux_llm_call_sink
        )
        if not isinstance(client, EpisodeWritingCompletion):
            raise RuntimeError(
                "episode writing needs an LLM client that can write episodes"
            )
        completion = client
    else:
        completion = StubEpisodeWritingCompletion()

    def _being_id_of(player_id: PlayerId) -> BeingId | None:
        acting = runtime._acting_being_for(player_id)
        return acting.being_id if acting is not None else None

    return PlayerEpisodeWriting(
        writer=EpisodeWriter(completion, runtime._being_episode_store),
        being_id_of=_being_id_of,
        turn_reader=turn_reader,
        environment_name_of=lambda pid: environment_entry_for_player(
            runtime.scenario, pid
        ).environment_name,
        persona_of=persona_of,
        trace_recorder_provider=lambda: runtime._trace_recorder,
        current_tick_provider=lambda: runtime.current_tick(),
    )


def create_world_runtime(
    scenario_path: Path,
    *,
    world_character: CharacterPromptInput | None = None,
    llm_turn_trigger: ILlmTurnTrigger | None = None,
    config: ResolvedLlmRuntimeConfig | None = None,
    round_number: int = 1,
) -> WorldRuntime:
    """シナリオ JSON からゲームランタイムを構築する。

    Args:
        llm_turn_trigger: 省略時は :class:`WorldStandaloneNoopLlmTurnTrigger`。
            スポットグラフのティック後フック用。プレゼン層のセッションでは
            ``runtime.set_simulation_llm_turn_trigger(…)`` で本物に差し替え可能。
        config: PR #448 (PR 3/6): LLM runtime 設定の単一窓口。省略時は
            ``ResolvedLlmRuntimeConfig.from_mapping()`` で空設定から既定値を
            resolve。entrypoint (run_scenario_experiment 等) で既に
            from_mapping() 済みの cfg を渡せば、**run_start trace と
            実 wiring の同一性を構造で保証する**ための引数。
        round_number: 同じシナリオを繰り返し遊ぶときの回の番号 (#1514)。
            シナリオの ``round_assignment`` を、シードとこの番号で割り当てる。
    """
    # 引数 cfg が来ていればそれを使う。来ていなければ空設定の既定値で構築する。
    # 実験に意味を持つ設定は環境変数から読まない。
    from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
        ResolvedLlmRuntimeConfig,
    )

    if config is None:
        config = ResolvedLlmRuntimeConfig.from_mapping()

    from ai_rpg_world.application.world_graph.world_tick_failure_isolation import (
        WorldTickFailureIsolator,
        WorldTickFailurePolicy,
    )

    world_tick_failure_isolator = WorldTickFailureIsolator(
        policy=WorldTickFailurePolicy.parse(config.world_tick_failure_policy),
        # recorder は set_trace_recorder で後から入るので、呼ばれた時点の値を見る。
        trace_recorder_provider=lambda: runtime._trace_recorder,
    )
    _record_after_commit_failure = world_tick_failure_isolator.after_commit_failure_observer(
        tick_provider=lambda: runtime.current_tick(),
    )
    from ai_rpg_world.application.llm.services.aux_llm_call_trace_sink import (
        AuxLlmCallTraceSink,
    )

    aux_llm_call_sink = AuxLlmCallTraceSink(
        trace_recorder_provider=lambda: runtime._trace_recorder,
        current_tick_provider=lambda: runtime.current_tick(),
    )

    loader = ScenarioLoader()
    scenario = loader.load_from_file(
        scenario_path,
        random_seed=config.scenario_random_seed,
        round_number=round_number,
    )

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

    # 記憶の指示は、組み上がった runtime が実際に出す欄とツールに合わせる (#1616)。
    # そのため組み立ては runtime を作り終えたあと (この関数の末尾) で行う。
    def _world_system_prompt(
        persona: str,
        *,
        episode_index_shown: bool,
        episode_recall_offered: bool,
    ) -> str:
        return build_world_system_prompt(
            world_title=scenario.metadata.title,
            persona_block=persona,
            safe_intro=safe_intro,
            has_goal=_has_goal,
            limits_actions=scenario.metadata.limits_actions,
            episode_index_shown=episode_index_shown,
            episode_recall_offered=episode_recall_offered,
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
    #   - 誰を知っているかは system prompt に書かない。入るときの紹介として
    #     Being に渡し、毎ターンのメッセージの【知っている人】に出す (#1520)
    personas_by_player_id: dict[int, str] = {}
    if scenario.player_spawns:
        # world_character に一致する spawn を特定
        world_spawn: PlayerSpawnConfig | None = None
        if world_character is not None:
            ec_cid = (world_character.character_id or "").strip()
            ec_name = (world_character.name or "").strip()
            for s in scenario.player_spawns:
                if (ec_cid and s.string_id == ec_cid) or (ec_name and s.name == ec_name):
                    world_spawn = s
                    break

        for spawn in scenario.player_spawns:
            viewer_role = str(spawn.initial_state.get("role") or "")
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
            personas_by_player_id[int(spawn.player_id)] = this_persona

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
        spec = ItemSpec(
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
        from ai_rpg_world.domain.common.value_object import WorldTick
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
    from ai_rpg_world.application.player.services.departed_position_store import (
        DepartedPositionStore,
    )
    from ai_rpg_world.application.player.services.fallen_body_registry import (
        FallenBodyRegistry,
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
    from ai_rpg_world.domain.item.aggregate.loot_table_aggregate import (
        LootEntry,
        LootTableAggregate,
    )
    from ai_rpg_world.domain.item.value_object.loot_table_id import LootTableId
    from ai_rpg_world.infrastructure.repository.in_memory_loot_table_repository import (
        InMemoryLootTableRepository,
    )
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
    from ai_rpg_world.application.world_runtime.world_random import world_random
    from ai_rpg_world.domain.world_graph.service.spot_interaction_service import (
        SpotInteractionService,
    )
    from ai_rpg_world.domain.world_graph.service.world_graph_effect_service import (
        WorldGraphEffectService,
    )

    _seed = config.scenario_random_seed
    _effect_service = WorldGraphEffectService(
        loot_table_repository=loot_table_repo,
        random_source=world_random(_seed, round_number, "loot"),
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
    pending_trade_offer_store = InMemoryPendingTradeOfferStore()
    trade_freeze_service = TradeFreezeService(
        pending_trade_offer_store=pending_trade_offer_store,
        player_inventory_repository=player_inventory_repo,
        player_status_repository=player_status_repo,
        item_repository=item_repo,
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
        # 納める gold は、同席取引に出して凍結中のぶんを差し引いて数える。
        available_gold_provider=trade_freeze_service.available_gold,
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

    item_transfer_dispatcher = CommandEventDispatcher(failure_observer=_record_after_commit_failure)
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
        spot_interior_repository=spot_interior_repo,
        item_transfer_command_scope_factory=item_transfer_scope_factory,
    )
    def _observe_expired_trade_offer(event: Any) -> None:
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
                EntityId.create(int(event.offerer_player_id))
            )
        except Exception:
            return
        pipeline_event_publisher.publish_all(
            (
                PlayerTradeOfferEvent.create(
                    aggregate_id=graph.graph_id,
                    aggregate_type="SpotGraphAggregate",
                    entity_id=EntityId.create(int(event.target_player_id)),
                    partner_entity_id=EntityId.create(
                        int(event.offerer_player_id)
                    ),
                    offerer_entity_id=EntityId.create(
                        int(event.offerer_player_id)
                    ),
                    spot_id=spot_id,
                    kind="expired",
                    gives_text=_describe_trade_side(event.gives),
                    asks_text=_describe_trade_side(event.asks),
                ),
            )
        )

    trade_offer_expiry_stage = TradeOfferExpiryStage(failure_isolator=world_tick_failure_isolator)
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
        **_optional_kwarg(
            "expires_in_ticks", scenario.player_trade_offer_expires_in_ticks
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
        # 同席取引と板が同じ gold を見る世界で、凍結ぶんの二重使用を防ぐ。
        trade_freeze_service=trade_freeze_service,
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
        **_optional_kwarg(
            "expires_in_ticks",
            scenario.market.order_expires_in_ticks if scenario.market else None,
        ),
        overflow_sink=refuse_overflow("市場の約定"),
    )
    # 期限を過ぎた注文を毎 tick 片付ける。**これを繋がないと、期限は
    # 宣言されているのに注文が永久に板へ残る** (v3 run で t33 の出品が
    # t80 まで生きていた)。
    market_order_expiry_stage = MarketOrderExpiryStage(
        market_service=market_service,
        failure_isolator=world_tick_failure_isolator,
    )
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

    def _resolve_item_state(item_instance_id_value: int) -> dict[str, Any] | None:
        """Phase D-3a: instance_id から state dict を引く軽量 resolver。

        地面アイテムの spoiled 表示用。InMemoryItemRepository.find_by_id は
        dict lookup なので毎 prompt 構築で叩いても問題なし。
        """
        from ai_rpg_world.domain.item.value_object.item_instance_id import (
            ItemInstanceId as _IID,
        )
        item = item_repo.find_by_id(_IID(item_instance_id_value))
        return dict(item.state) if item is not None else None

    def _build_inventory(pid: PlayerId) -> tuple[Any, ...]:
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
        seen_groups: dict[tuple[int, bool], list[Any]] = {}
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
                    (item_spec_definition.usage_hint or "")
                    if item_spec_definition is not None
                    else (item.item_spec.usage_hint or "")
                )
                category_value = (
                    item_spec_definition.category
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

    from ai_rpg_world.domain.world.enum.weather_enum import WeatherTypeEnum
    from ai_rpg_world.domain.world.value_object.weather_state import WeatherState

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
    day_night_stage: SpotGraphDayNightStageService | None = None
    day_night_config = scenario.day_night_config
    if day_night_config is not None:
        day_night_stage = SpotGraphDayNightStageService(
            cycle=day_night_config.cycle,
        )

    # 光源アイテムを自動検出
    light_source_item_spec_ids = frozenset(
        spec.item_spec_id
        for spec in item_spec_repo.find_all()
        if spec.is_light_source
    )

    def _owned_item_spec_ids_provider(entity_id: int) -> frozenset[Any]:
        inv = player_inventory_repo.find_by_id(PlayerId(entity_id))
        if inv is None:
            return frozenset()
        return collect_owned_item_spec_ids_from_inventory(inv, item_repo)

    def _build_phase_label_resolver(
        day_night_config: ScenarioDayNightConfig | None,
    ) -> Callable[[str], str | None] | None:
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

    def _build_monster_view_provider_for_runtime(_monster_repo: Any) -> Any:
        """state_builder に渡す monster_view_provider を遅延構築する小ヘルパ。

        spot_graph_monster_view.build_monster_view_provider を呼ぶだけだが、
        circular import を避けるために関数内 import に寄せた。
        """
        from ai_rpg_world.application.world_graph.spot_graph_monster_view import (
            build_monster_view_provider,
        )
        return build_monster_view_provider(_monster_repo)

    def _describe_trade_side(side: Any) -> str:
        """取引の片側を、人が読める短い形にする。"""
        parts = [
            f"{_resolve_item_spec_name(spec_id)} {quantity}つ"
            for spec_id, quantity in side.items
        ]
        if side.gold:
            parts.append(f"{side.gold}G")
        return "・".join(parts) if parts else "なし"

    def _incoming_trade_offers_for(player_id: int) -> tuple[Any, ...]:
        """その人に来ている申し出を、表示用の形にして返す。"""
        from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
            SpotGraphTradeOfferEntry,
        )

        current = time_provider.get_current_tick().value
        return tuple(
            SpotGraphTradeOfferEntry(
                # 申し出た人は一覧と同じ呼び方で出す。応じる対象の名前と揃える (#1581)。
                offerer_name=player_acquaintances.call_name(
                    PlayerId(player_id), PlayerId(int(offer.offerer_player_id))
                ),
                gives_text=_describe_trade_side(offer.gives),
                asks_text=_describe_trade_side(offer.asks),
                remaining_ticks=max(0, offer.expires_at_tick - current),
            )
            for offer in pending_trade_offer_store.list_for_target(PlayerId(player_id))
        )

    def _resolve_item_spec_name(spec_id_value: int) -> str:
        """item_spec_id → 表示名解決。地面アイテムの prompt 表示などで使う。"""
        from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId as _ISpecId
        spec = item_spec_repo.find_by_id(_ISpecId.create(spec_id_value))
        if spec is None:
            return ""
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
        def found_prose(name: str) -> str:
            if is_dead:
                return f"{name}が倒れているのを見つけた。動かない。"
            return f"{name}が倒れているのを見つけた。"

        name = victim_name or "誰か"
        prose = found_prose(name)
        # cue が読むのは int の spot_id_value。get_player_spot_id は trace 用の
        # 文字列を返すので使えない。
        body = runtime._fallen_body_registry.find(PlayerId(int(victim_entity_id)))
        spot_id_value = int(body.spot_id) if body is not None else None
        structured = {
            "type": "fallen_body_found",
            "actor": name,
            "is_dead": bool(is_dead),
        }
        if spot_id_value is not None:
            structured["spot_id_value"] = spot_id_value
        # 体は見えているので届けるが、会っていない相手なら名前は分からない。
        if_subject_unknown = (
            SubjectUnknownView(
                prose=found_prose("誰か"),
                structured={k: v for k, v in structured.items() if k != "actor"},
            )
            if victim_name
            else None
        )
        runtime._emit_observation_directly(
            pid,
            ObservationOutput(
                prose=prose,
                structured=structured,
                observation_category="social",
                schedules_turn=True,
                # 死体を見つけたら足は止まる。移動を続けるほうが不自然。
                breaks_movement=True,
                subject_name=victim_name or None,
                if_subject_unknown=if_subject_unknown,
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
        return int(tp.get_current_tick().value)

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
        viewer_name_resolver=lambda viewer_id, other_id: player_acquaintances.call_name(
            PlayerId(viewer_id), PlayerId(other_id)
        ),
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
        # 形には戻さない。`hidden` と宣言した属性も本人に見せない (#1546)。
        hidden_player_state_keys=build_recorded_player_state_tick_keys(
            list(scenario.graph.iter_spot_nodes()),
            scenario.interiors,
            scenario.player_interactions,
        )
        | scenario.player_attribute_specs.hidden_names(),
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
        item_repository=item_repo,
        item_spec_repository=item_spec_repo,
        event_removal_messages={
            item_def.spec_id.value: item_def.event_removal_message
            for item_def in scenario.item_spec_definitions
            if item_def.event_removal_message
        },
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
    # LLM 経路 (summary_service / persona_resolver) は
    # 旧来 setter で後注入していたが、ctor 注入に統一して呼び忘れ silent failure
    # を構造で排除。trace_recorder / current_tick は runtime instance に依存する
    # ため別経路 (set_trace_recorder) で差し替え (NullObject 経由で安全)。
    short_term_memory = _build_short_term_memory(
        config,
        scenario=scenario,
        world_character=world_character,
        persona_block=persona_block,
        event_store=recent_event_store,
        aux_llm_call_sink=aux_llm_call_sink,
        # runtime はこのあとで組むが、畳むのは tick が始まってからなので間に合う。
        on_compacted=lambda pid, entries: runtime._write_compacted_episodes(pid, entries),
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

        def owned_item_spec_ids_for(self, player_id: PlayerId) -> frozenset[ItemSpecId]:
            inv = self._player_inventory_repository.find_by_id(player_id)
            if inv is None:
                return frozenset()
            return collect_owned_item_spec_ids_from_inventory(inv, self._item_repository)

        def world_flags(self) -> frozenset[str]:
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
        failure_isolator=world_tick_failure_isolator,
    )
    travel_stage.set_departed_checker(player_perception_policy.is_departed)

    def _record_arrival_in_history(player_id: PlayerId) -> None:
        """到着したことを行動履歴に残す。

        **移動中は手番が来ない** (turn_trigger が is_traveling を見て飛ばす)
        ので、エージェントから見ると宣言した tick の次に意識が戻るのは到着
        した tick になる。ところが履歴には出発 (「◯◯へ移動中」) しか残らず、
        **着いた瞬間の行が無かった**。その結果、到着済みなのに同じ移動を
        もう一度宣言する空転が起きる (v2 run でドナが 5 回、run 全体で 11 件)。

        現在地の 1 行は静的な表示なので、時系列を追う側の目には入りにくい。
        **出来事として残す。**
        """
        try:
            spot_name = runtime.get_player_spot_name(player_id)
        except Exception:
            # 盤から外れた人は場所の名前を持たない。到着の行を書かないだけの正常な経路。
            logger.debug(
                "arrival history: spot name unavailable for player %s",
                player_id.value,
            )
            return
        try:
            runtime._record_action_result(
                player_id,
                f"「{spot_name}」に着いた",
                f"「{spot_name}」に到着した。ここから次の行動を選べる。",
                tool_name=TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
                success=True,
            )
        except Exception as exc:
            runtime._record_world_tick_follow_up_failure(
                exc,
                stage="travel.arrival_history",
                target_kind="player",
                target_id=player_id.value,
                player_id=player_id.value,
            )

    travel_stage.add_arrival_observer(_record_arrival_in_history)
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
    # 天候は条件評価と消費順を共有しない別の乱数にする。どちらもシードと回の
    # 番号から作る (world_random)。シードが無ければ非決定的。
    _scenario_random = world_random(_seed, round_number, "scenario")
    _weather_random = world_random(_seed, round_number, "weather")
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
        failure_isolator=world_tick_failure_isolator,
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
        failure_isolator=world_tick_failure_isolator,
        bindings=scenario.reactive_object_state_bindings,
        condition_evaluator=condition_evaluator,
        predicate_trace_emitter=predicate_trace_emitter,
    )
    sync_action_registry = SynchronizedActionRegistry(world_flag_state)
    sync_resolver_stage = SynchronizedActionResolverStageService(
        failure_isolator=world_tick_failure_isolator,
        groups=scenario.synchronized_action_groups,
        registry=sync_action_registry,
        world_flag_state=world_flag_state,
        effect_service=_effect_service,
    )
    environment_stage = SpotGraphEnvironmentStageService(
        weather_state_provider=lambda: weather_holder["state"],
        weather_state_setter=lambda s: weather_holder.__setitem__("state", s),
        update_interval_ticks=(
            weather_config.update_interval_ticks
            if weather_config is not None and weather_config.enabled
            else 6
        ),
        random_source=_weather_random,
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
        starvation_damage_per_tick=starvation_dmg,
        # 空腹と疲労の進み方もシナリオの宣言から取る。**ここで渡し忘れると、
        # 宣言しても既定のまま進む** = 変えたつもりで変わっていない run に
        # なるので、宣言が実際に効くところまでを試験で見ている。
        rates={
            NeedType.HUNGER: needs_config.hunger_per_tick,
            NeedType.FATIGUE: needs_config.fatigue_per_tick,
        },
    )

    # PR #2: 状態異常 tick 進行 stage。active_effects の継続効果適用 + 期限
    # 切れ掃除を担う。repositoryとevent収集口はCommandScopeから取得する。
    from ai_rpg_world.application.world_graph.status_effects_tick_stage_service import (
        StatusEffectsTickStageService,
    )
    status_effects_stage = StatusEffectsTickStageService()

    # Phase B-2a: モンスター攻撃のオーケストレーターと behavior tick service。
    # placements が空ならどちらも構築しないことで、既存シナリオ
    # (廃病院 等) の挙動を一切変えない。
    monster_attack_orchestrator = None
    monster_behavior_service = None
    monster_behavior_stage = None
    monster_spawn_stage = None  # Phase B-2b: 条件付き placement の動的 spawn
    if scenario.monster_placements:
        from ai_rpg_world.application.monster.services.spot_monster_behavior_tick_service import (
            SpotMonsterBehaviorTickService,
        )
        from ai_rpg_world.application.world_graph.spot_attack_orchestrator import (
            SpotAttackOrchestrator,
        )

        monster_attack_orchestrator = SpotAttackOrchestrator(
            spot_graph_repository=spot_graph_repo,
            monster_repository=monster_repo,
            player_status_repository=player_status_repo,
            random_source=world_random(_seed, round_number, "attack").random,
            # PR-K: event_publisher は runtime 構築後に pipeline_event_publisher
            # が用意されてから setter で後付け注入する (= needs_decay_stage
            # 等と同じ pattern)。bind 前は致命攻撃で events が積まれても publish
            # されない (= 旧挙動互換)。
        )
        monster_behavior_service = SpotMonsterBehaviorTickService(
            failure_isolator=world_tick_failure_isolator,
            spot_graph_repository=spot_graph_repo,
            monster_repository=monster_repo,
            player_status_repository=player_status_repo,
            attack_orchestrator=monster_attack_orchestrator,
            random_source=world_random(_seed, round_number, "monster_behavior"),
            world_flags_provider=world_flag_state.as_frozen_set,
            spot_interior_repository=spot_interior_repo,
        )

        # SpotGraphSimulationApplicationService の tick stage は run(tick) を
        # 要求するが behavior service は tick(tick) を持つ。薄いアダプタで橋渡し。
        class _MonsterBehaviorTickStageAdapter:
            def __init__(self, service: Any) -> None:
                self._service = service

            def run(self, tick: Any) -> None:
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
                spawn_condition = placement.spawn_condition
                slots.append(MonsterSpawnSlot(
                    slot_key=slot_key,
                    template=template,
                    spot_id=SpotId.create(spot_int),
                    coordinate=Coordinate(
                        x=placement.coordinate_x,
                        y=placement.coordinate_y,
                        z=placement.coordinate_z,
                    ),
                    day_night_phase_names=(
                        spawn_condition.day_night_phase_names
                        if spawn_condition is not None
                        else ()
                    ),
                    required_flags=(
                        spawn_condition.required_flags if spawn_condition is not None else ()
                    ),
                    forbidden_flags=(
                        spawn_condition.forbidden_flags if spawn_condition is not None else ()
                    ),
                    weather_type_names=(
                        spawn_condition.weather_type_names
                        if spawn_condition is not None
                        else ()
                    ),
                ))

            monster_spawn_service = SpotGraphMonsterSpawnStageService(
                failure_isolator=world_tick_failure_isolator,
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
    spoilable_specs: dict[ItemSpecId, int] = {}
    for item_def in scenario.item_spec_definitions:
        if item_def.spoils_after_ticks is not None:
            spoilable_specs[item_def.spec_id] = item_def.spoils_after_ticks
    if spoilable_specs:
        from ai_rpg_world.application.world_graph.food_spoilage_stage_service import (
            FoodSpoilageStageService,
        )

        food_spoilage_stage = FoodSpoilageStageService(
            spoilable_specs=spoilable_specs,
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
    from ai_rpg_world.application.player.services.player_death_grace_tick_stage import (
        PlayerDeathGraceTickStage,
    )
    from ai_rpg_world.application.player.services.player_death_grace_timer import (
        PlayerDeathGraceTimer,
    )
    death_grace_timer = PlayerDeathGraceTimer()
    death_grace_stage = PlayerDeathGraceTickStage(
        failure_isolator=world_tick_failure_isolator,
        outcome_registry=outcome_registry,
        grace_timer=death_grace_timer,
        fallen_body_registry=fallen_body_registry,
        departed_position_store=departed_position_store,
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
            failure_isolator=world_tick_failure_isolator,
            rules=scenario.player_outcome_rules,
            outcome_registry=outcome_registry,
            condition_evaluator=condition_evaluator,
            progress_store=scenario_event_progress,
            graph_provider=lambda: spot_graph_repo.find_graph(),
            player_ids=[PlayerId(spawn.player_id) for spawn in scenario.player_spawns],
            predicate_trace_emitter=predicate_trace_emitter,
        )

    def _flush_graph_events() -> None:
        # runtime はまだ未代入なので、呼出時に名前解決させる。
        runtime._process_graph_events()
        runtime._evaluate_distant_cue_appearances()

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
        graph_event_flusher=_flush_graph_events,
        failure_isolator=world_tick_failure_isolator,
    )

    memory_turn_clock = InMemoryMemoryTurnClock()
    acquaintance_store = InMemoryAcquaintanceRepository()

    def _being_id_of(player_id: PlayerId) -> BeingId | None:
        resolver: BeingAttachmentResolver | None = runtime.aux_being_resolver
        if resolver is None:
            return None
        return resolver.resolve_being_id(runtime.aux_being_default_world_id, player_id)

    def _players_share_a_spot(a: PlayerId, b: PlayerId) -> bool:
        """世界に居ない人 (死んで場所を離れた人など) は、誰とも同じ場所にいない。"""
        from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
            EntityNotInGraphException,
        )

        graph = spot_graph_repo.find_graph()
        try:
            return graph.get_entity_spot(
                EntityId.create(int(a.value))
            ) == graph.get_entity_spot(EntityId.create(int(b.value)))
        except EntityNotInGraphException:
            return False

    player_acquaintances = PlayerAcquaintances(
        store=acquaintance_store,
        being_id_of=_being_id_of,
        turn_reader=memory_turn_clock,
        environment_name=scenario.metadata.title,
        names_by_player_id={
            int(spawn.player_id): spawn.name for spawn in scenario.player_spawns
        },
        appearances_by_player_id={
            int(spawn.player_id): spawn.appearance
            for spawn in scenario.player_spawns
            if spawn.appearance is not None
        },
        co_present=_players_share_a_spot,
        trace_recorder_provider=lambda: runtime._trace_recorder,
        current_tick_provider=lambda: runtime.current_tick(),
    )

    runtime = WorldRuntime(
        scenario=scenario,
        _aux_llm_call_sink=aux_llm_call_sink,
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
            acquaintances=player_acquaintances,
            executed_turn_provider=lambda pid: runtime._execution_turns.get(int(pid.value), 0),
        ),
        _obs_pipeline=obs_pipeline,
        _obs_buffer=obs_buffer,
        _recent_event_store=recent_event_store,
        _short_term_memory=short_term_memory,
        _action_result_store=action_result_store,
        _encounter_memory=encounter_memory,
        _memory_turn_clock=memory_turn_clock,
        _acquaintance_store=acquaintance_store,
        _player_acquaintances=player_acquaintances,
        _time_provider=time_provider,
        _simulation_service=simulation_service,
        _world_tick_failure_isolator=world_tick_failure_isolator,
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
        reason_first_two_step_enabled=config.reason_first_two_step_enabled,
        _runtime_config=config,
    )
    travel_stage.set_on_travel_tick_committed(
        runtime._record_committed_player_travel_tick
    )
    travel_stage.add_blocked_observer(runtime._report_travel_blocked)
    world_flag_state.set_change_callback(runtime._record_world_flag_change)
    scenario_event_stage.set_message_callback(
        runtime._append_scenario_event_observation
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
        observers=[
            encounter_collector.on_observation,
            player_acquaintances.on_observation,
        ],
        recipient_view=player_acquaintances.view_for,
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
        # 救助・取り残し・死亡は、名前を伏せても知らない誰かがいることが分かって
        # しまう。追放は会議の場で全員が見て決めたことなので、全員へ届ける。
        withheld_from_strangers = new_outcome is not PlayerOutcomeEnum.EJECTED
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
            subject_name=actor_name if withheld_from_strangers else None,
            if_subject_unknown=(
                WithheldFromStrangers() if withheld_from_strangers else None
            ),
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

    # DEAD時の退場位置はdeath grace commandがcommit前に更新する。registryの
    # callbackへ状態変更を残さず、確定後には観測だけを流す。
    outcome_registry.register_callback(_broadcast_outcome_change)
    # Issue #621: ダウン → DEAD 即時確定をやめ、30 tick の猶予を設ける。
    # grace_timer / grace_stage は simulation_service 構築時に作成済み。
    # 身体と猶予を更新するhandlerは、後段のCommandEventDispatcherへ
    # commit前必須処理として登録する。pipelineには観測処理だけを残す。
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
            except Exception as exc:
                runtime._record_world_tick_follow_up_failure(
                    exc,
                    stage="player_downed.killer_saw_body",
                    target_kind="player",
                    target_id=int(killer),
                    player_id=int(killer),
                )

    # 加害者の遭遇記録は確定後の最善努力処理。身体・猶予の正本更新には使わない。
    pipeline_event_publisher.register_handler(
        PlayerDownedEvent, _MarkKillerAsHavingSeenTheBody()
    )
    record_fallen_body_handler = RecordFallenBodyHandler(
        registry=fallen_body_registry,
        spot_graph_repository=spot_graph_repo,
        current_tick_provider=lambda: int(runtime.current_tick()),
    )
    downed_outcome_handler = PlayerDownedOutcomeHandler(
        outcome_registry=outcome_registry,
        grace_timer=death_grace_timer,
        current_tick_provider=lambda: int(runtime.current_tick()),
    )
    # Issue #621 Phase 5: revive 時の post hoc summary 注入。commit前取消は
    # event_idに対応するdowned_at_tickをtimerへ退避するため、確定後でも正確な
    # 「N tick の間意識を失っていた」を組み立てられる。
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
    remove_fallen_body_handler = RemoveFallenBodyOnReviveHandler(
        fallen_body_registry
    )
    pipeline_event_publisher.register_handler(
        PlayerRevivedEvent,
        PlayerRevivedPostHocObservationHandler(
            grace_timer=death_grace_timer,
            observation_appender=observation_appender,
            current_tick_provider=lambda: int(runtime.current_tick()),
            caregiver_name_resolver=lambda pid: _caregiver_name_by_pid.get(int(pid)),
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
            actor_name_resolver=lambda pid: _caregiver_name_by_pid.get(int(pid)),
        ),
    )

    # 身体・猶予タイマーの正本は下のCommandEventDispatcherでcommit前に更新する。
    # pipelineは観測だけを担い、直接publisherから状態を補完しない。
    # ConsumableUsedEventの状態効果はuse_item専用CommandScopeのcommit前必須処理へ
    # 移した。ここでpipeline side handlerへ登録すると、commit後に同じ効果が
    # 二重適用されるため、pipelineは観測配送だけを担当する。
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

    # 成功eventはinteractionのCommandContextからcommit後に配送する。
    # このpublisherは前提条件拒否をrollback後の確定状態から観測する専用口。
    interaction_service.set_event_publisher(pipeline_event_publisher)
    # 通常interactionと会議開始は、それぞれ独立したCommandScopeで確定する。
    # CALL_MEETINGを通常interactionの内側へ入れず、専用scopeを順に開始することで
    # 入れ子transactionを避ける。成功eventはどちらもcommit後だけ配送する。
    from ai_rpg_world.domain.common.domain_event import BaseDomainEvent
    from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
        MeetingVoteResolvedEvent,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_food_spoilage_command_repository_provider import (
        InMemoryFoodSpoilageCommandRepositoryProviderFactory,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_interaction_command_repository_provider import (
        InMemoryInteractionCommandRepositoryProviderFactory,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_market_order_expiry_command_repository_provider import (
        InMemoryMarketOrderExpiryCommandRepositoryProviderFactory,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_meeting_command_repository_provider import (
        InMemoryMeetingCommandRepositoryProviderFactory,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_monster_behavior_command_repository_provider import (
        InMemoryMonsterBehaviorCommandRepositoryProviderFactory,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_monster_spawn_command_repository_provider import (
        InMemoryMonsterSpawnCommandRepositoryProviderFactory,
    )
    from ai_rpg_world.infrastructure.repository.in_memory_movement_command_repository_provider import (
        InMemoryMovementCommandRepositoryProviderFactory,
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
    from ai_rpg_world.infrastructure.repository.in_memory_trade_offer_expiry_command_repository_provider import (
        InMemoryTradeOfferExpiryCommandRepositoryProviderFactory,
    )
    from ai_rpg_world.infrastructure.unit_of_work.interaction_rollback_participants import (
        build_day_night_rollback_participants,
        build_death_grace_rollback_participants,
        build_exploration_rollback_participants,
        build_interaction_rollback_participants,
        build_market_order_expiry_rollback_participants,
        build_meeting_rollback_participants,
        build_monster_behavior_rollback_participants,
        build_monster_spawn_rollback_participants,
        build_movement_rollback_participants,
        build_player_lifecycle_rollback_participants,
        build_player_outcome_rule_rollback_participants,
        build_player_trade_rollback_participants,
        build_reactive_rollback_participants,
        build_scenario_event_rollback_participants,
        build_synchronized_action_rollback_participants,
        build_trade_offer_expiry_rollback_participants,
        build_weather_rollback_participants,
    )
    from ai_rpg_world.infrastructure.unit_of_work.rollback_participant_transaction_adapter import (
        RollbackParticipantTransactionFactory,
    )

    def _apply_player_lifecycle_before_commit(event: Any, context: Any) -> None:
        """status eventに付随する身体・猶予を同じcommand内で確定する。"""
        del context
        if isinstance(event, PlayerDownedEvent):
            record_fallen_body_handler.handle(event)
            downed_outcome_handler.handle(event)
            return
        if isinstance(event, PlayerRevivedEvent):
            remove_fallen_body_handler.handle(event)
            death_grace_timer.cancel(
                event.aggregate_id,
                event_id=event.event_id,
            )

    interaction_dispatcher = CommandEventDispatcher(failure_observer=_record_after_commit_failure)
    interaction_dispatcher.register_required_before_commit(
        PlayerDownedEvent,
        _apply_player_lifecycle_before_commit,
    )
    interaction_dispatcher.register_required_before_commit(
        PlayerRevivedEvent,
        _apply_player_lifecycle_before_commit,
    )
    interaction_dispatcher.register_after_commit(
        BaseDomainEvent,
        lambda event: pipeline_event_publisher.publish_all((event,)),
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    # use_itemは消費・在庫・PlayerStatus効果を同じtransactionへ入れる。
    # ConsumableUsedEventはまずcommit前必須handlerでscope内statusへ適用し、
    # 確定後にだけ観測pipelineへ渡す。
    from ai_rpg_world.application.common.command_context_event_publisher import (
        CommandContextEventPublisher,
    )
    from ai_rpg_world.application.world.handlers.consumable_effect_handler import (
        ConsumableEffectHandler,
    )
    from ai_rpg_world.domain.item.event.item_event import ConsumableUsedEvent

    use_item_dispatcher = CommandEventDispatcher(failure_observer=_record_after_commit_failure)

    def _apply_consumable_effect_before_commit(event: Any, context: Any) -> None:
        repositories = context.repositories
        ConsumableEffectHandler(
            item_spec_repository=repositories.item_specs,
            player_status_repository=repositories.player_statuses,
            event_publisher=CommandContextEventPublisher(context),
        ).handle(event)

    use_item_dispatcher.register_required_before_commit(
        ConsumableUsedEvent,
        _apply_consumable_effect_before_commit,
    )
    use_item_dispatcher.register_required_before_commit(
        PlayerDownedEvent,
        _apply_player_lifecycle_before_commit,
    )
    use_item_dispatcher.register_required_before_commit(
        PlayerRevivedEvent,
        _apply_player_lifecycle_before_commit,
    )
    use_item_dispatcher.register_after_commit(
        BaseDomainEvent,
        lambda event: pipeline_event_publisher.publish_all((event,)),
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    player_lifecycle_participants = build_player_lifecycle_rollback_participants(
        grace_timer=death_grace_timer,
        fallen_bodies=fallen_body_registry,
    )
    use_item_scope_factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            participants=player_lifecycle_participants,
        ),
        sync_dispatcher=use_item_dispatcher,
        after_commit_handoff=use_item_dispatcher,
        repository_provider_factory=(
            InMemoryInteractionCommandRepositoryProviderFactory(
                spot_graph=spot_graph_repo,
                item_specs=item_spec_repo,
            )
        ),
    )
    runtime._use_item_command_scope_factory = use_item_scope_factory
    exploration_scope_factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            participants=build_exploration_rollback_participants(
                progress=exploration_progress,
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
    exploration_service.set_command_scope_factory(exploration_scope_factory)
    player_trade_scope_factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            participants=build_player_trade_rollback_participants(
                pending_trade_offers=pending_trade_offer_store,
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
    player_trade_service.set_command_scope_factory(player_trade_scope_factory)
    merchant_trade_scope_factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            participants=build_player_trade_rollback_participants(
                pending_trade_offers=pending_trade_offer_store,
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
    merchant_trade_service.set_command_scope_factory(merchant_trade_scope_factory)
    market_command_scope_factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            participants=(
                *build_market_order_expiry_rollback_participants(
                    market_board=market_board_store,
                ),
                *build_player_trade_rollback_participants(
                    pending_trade_offers=pending_trade_offer_store,
                ),
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
    market_service.set_command_scope_factory(market_command_scope_factory)
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
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            participants=player_lifecycle_participants,
        ),
        sync_dispatcher=interaction_dispatcher,
        after_commit_handoff=interaction_dispatcher,
        repository_provider_factory=(
            InMemoryPlayerStatusTickCommandRepositoryProviderFactory()
        ),
    )
    needs_decay_stage.set_command_scope_factory(player_status_tick_scope_factory)
    status_effects_stage.set_command_scope_factory(player_status_tick_scope_factory)
    if food_spoilage_stage is not None:
        from ai_rpg_world.domain.item.event.item_event import ItemSpoiledEvent

        food_spoilage_dispatcher = CommandEventDispatcher(failure_observer=_record_after_commit_failure)
        food_spoilage_dispatcher.register_after_commit(
            ItemSpoiledEvent,
            lambda event: runtime._append_food_spoiled_batch_observation(
                ((event.item_instance_id, event.item_spec_id, event.spec_name),)
            ),
            channel=DeliveryChannel.OBSERVATION,
            guarantee=DeliveryGuarantee.BEST_EFFORT,
        )
        food_spoilage_scope_factory = CommandScopeFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            sync_dispatcher=food_spoilage_dispatcher,
            after_commit_handoff=food_spoilage_dispatcher,
            repository_provider_factory=(
                InMemoryFoodSpoilageCommandRepositoryProviderFactory()
            ),
        )
        food_spoilage_stage.set_command_scope_factory(food_spoilage_scope_factory)
    from ai_rpg_world.domain.trade.event.trade_event import TradeOfferExpiredEvent

    trade_offer_expiry_dispatcher = CommandEventDispatcher(failure_observer=_record_after_commit_failure)
    trade_offer_expiry_dispatcher.register_after_commit(
        TradeOfferExpiredEvent,
        _observe_expired_trade_offer,
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    trade_offer_expiry_scope_factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            participants=build_trade_offer_expiry_rollback_participants(
                pending_trade_offers=pending_trade_offer_store,
            ),
        ),
        sync_dispatcher=trade_offer_expiry_dispatcher,
        after_commit_handoff=trade_offer_expiry_dispatcher,
        repository_provider_factory=(
            InMemoryTradeOfferExpiryCommandRepositoryProviderFactory(
                pending_trade_offer_store
            )
        ),
    )
    trade_offer_expiry_stage.set_command_scope_factory(
        trade_offer_expiry_scope_factory
    )
    market_order_expiry_scope_factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            participants=build_market_order_expiry_rollback_participants(
                market_board=market_board_store,
            ),
        ),
        sync_dispatcher=interaction_dispatcher,
        after_commit_handoff=interaction_dispatcher,
        repository_provider_factory=(
            InMemoryMarketOrderExpiryCommandRepositoryProviderFactory()
        ),
    )
    market_order_expiry_stage.set_command_scope_factory(
        market_order_expiry_scope_factory
    )
    if player_outcome_rule_stage is not None:
        player_outcome_rule_scope_factory: CommandScopeFactory[Any] = CommandScopeFactory(
            RollbackParticipantTransactionFactory(
                InMemoryUnitOfWorkTransactionFactory(data_store),
                participants=build_player_outcome_rule_rollback_participants(
                    player_outcomes=outcome_registry,
                    progress=scenario_event_progress,
                    condition_evaluator=condition_evaluator,
                ),
            ),
            sync_dispatcher=interaction_dispatcher,
            after_commit_handoff=interaction_dispatcher,
        )
        player_outcome_rule_stage.set_command_scope_factory(
            player_outcome_rule_scope_factory
        )
    death_grace_scope_factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            participants=build_death_grace_rollback_participants(
                player_outcomes=outcome_registry,
                grace_timer=death_grace_timer,
                fallen_bodies=fallen_body_registry,
                departed_positions=departed_position_store,
            ),
        ),
        sync_dispatcher=interaction_dispatcher,
        after_commit_handoff=interaction_dispatcher,
        repository_provider_factory=(
            InMemoryPlayerStatusTickCommandRepositoryProviderFactory()
        ),
    )
    death_grace_stage.set_command_scope_factory(death_grace_scope_factory)
    scenario_event_scope_factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            participants=(
                *build_scenario_event_rollback_participants(
                    world_flags=world_flag_state,
                    spot_graph=spot_graph_repo,
                    progress=scenario_event_progress,
                ),
                *player_lifecycle_participants,
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
    from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
        ConnectionStateChangedEvent,
    )
    from ai_rpg_world.domain.world_graph.event.synchronized_action_event import (
        SynchronizedActionMessageEvent,
    )

    synchronized_action_dispatcher = CommandEventDispatcher(failure_observer=_record_after_commit_failure)
    synchronized_action_dispatcher.register_after_commit(
        ConnectionStateChangedEvent,
        lambda event: pipeline_event_publisher.publish_all((event,)),
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    synchronized_action_dispatcher.register_after_commit(
        SynchronizedActionMessageEvent,
        lambda event: runtime._append_synchronized_action_observation(
            event.aggregate_id,
            event.outcome,
            event.recipient_ids,
            event.message,
        ),
        channel=DeliveryChannel.OBSERVATION,
        guarantee=DeliveryGuarantee.BEST_EFFORT,
    )
    synchronized_action_scope_factory = CommandScopeFactory(
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            participants=build_synchronized_action_rollback_participants(
                world_flags=world_flag_state,
                spot_graph=spot_graph_repo,
            ),
        ),
        sync_dispatcher=synchronized_action_dispatcher,
        after_commit_handoff=synchronized_action_dispatcher,
        repository_provider_factory=(
            InMemorySynchronizedActionCommandRepositoryProviderFactory(
                spot_graph=spot_graph_repo,
            )
        ),
    )
    sync_resolver_stage.set_command_scope_factory(
        synchronized_action_scope_factory
    )
    from ai_rpg_world.domain.world_graph.event.environment_event import (
        SpotGraphDayNightPhaseChangedEvent,
        SpotGraphWeatherChangedEvent,
    )
    from ai_rpg_world.domain.world_graph.event.spot_graph_event import (
        TimeOfDayChangedEvent,
    )

    weather_dispatcher = CommandEventDispatcher(failure_observer=_record_after_commit_failure)
    if weather_config is None or weather_config.announce_changes:
        weather_dispatcher.register_after_commit(
            SpotGraphWeatherChangedEvent,
            lambda event: runtime._append_weather_observation(event.weather_state),
            channel=DeliveryChannel.OBSERVATION,
            guarantee=DeliveryGuarantee.BEST_EFFORT,
        )
    weather_scope_factory = CommandScopeFactory[object](
        RollbackParticipantTransactionFactory(
            InMemoryUnitOfWorkTransactionFactory(data_store),
            participants=build_weather_rollback_participants(
                stage=environment_stage,
            ),
        ),
        sync_dispatcher=weather_dispatcher,
        after_commit_handoff=weather_dispatcher,
    )
    environment_stage.set_command_scope_factory(weather_scope_factory)
    if day_night_stage is not None:
        day_night_dispatcher = CommandEventDispatcher(failure_observer=_record_after_commit_failure)
        if day_night_config is not None and day_night_config.announce_changes:

            def _observe_day_night_transition(
                event: SpotGraphDayNightPhaseChangedEvent,
            ) -> None:
                graph = spot_graph_repo.find_graph()
                pipeline_event_publisher.publish_all((
                    TimeOfDayChangedEvent.create(
                        aggregate_id=graph.graph_id,
                        aggregate_type="SpotGraphAggregate",
                        old_phase_name=event.old_time.phase_name,
                        new_phase_name=event.new_time.phase_name,
                        new_display_text=event.new_time.display_text,
                        new_is_dark=event.new_time.is_dark,
                    ),
                ))

            day_night_dispatcher.register_after_commit(
                SpotGraphDayNightPhaseChangedEvent,
                _observe_day_night_transition,
                channel=DeliveryChannel.OBSERVATION,
                guarantee=DeliveryGuarantee.BEST_EFFORT,
            )
        day_night_scope_factory = CommandScopeFactory[object](
            RollbackParticipantTransactionFactory(
                InMemoryUnitOfWorkTransactionFactory(data_store),
                participants=build_day_night_rollback_participants(
                    stage=day_night_stage,
                ),
            ),
            sync_dispatcher=day_night_dispatcher,
            after_commit_handoff=day_night_dispatcher,
        )
        day_night_stage.set_command_scope_factory(day_night_scope_factory)
    if monster_behavior_service is not None:
        monster_behavior_scope_factory = CommandScopeFactory(
            RollbackParticipantTransactionFactory(
                InMemoryUnitOfWorkTransactionFactory(data_store),
                participants=(
                    *build_monster_behavior_rollback_participants(
                        spot_graph=spot_graph_repo,
                        service=monster_behavior_service,
                    ),
                    *player_lifecycle_participants,
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
    interaction_participants = (
        *build_interaction_rollback_participants(
            world_flags=world_flag_state,
            cooldowns=interaction_cooldown_store,
            departed_positions=departed_position_store,
            spot_graph=spot_graph_repo,
        ),
        # DEPOSIT_GOLD_TO_OBJECT は同席取引に凍結中のgoldを差し引く。
        # 予約状態の読取りから支払い確定まで同じ所有権を持ち、並行する
        # offer更新との間に二重使用の競合窓を作らない。
        *build_player_trade_rollback_participants(
            pending_trade_offers=pending_trade_offer_store,
        ),
        *player_lifecycle_participants,
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
    # tend_to_playerは対象statusの復活とPlayerRevivedEventを同じscopeで確定する。
    # 既存interactionと同じrepository束・commit後dispatcherを再利用する。
    runtime._tend_to_player_command_scope_factory = interaction_scope_factory
    runtime._prepare_action_command_scope_factory = interaction_scope_factory
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

    # 会った相手は Being が覚えるので、初期配置の同席を記録する前に全員の Being を用意する。
    # 下の起動時の検査は画面を組んで知り合いの記録を読むので、その前に済ませる。
    # prompt dataset の各行も being_id を要るので、それより先に組む。
    # 用意に失敗したら起動を止める。誰を知っているかはプロンプトの前提なので、
    # 欠けたまま走ると、実験の条件が run のどこにも残らないまま変わる。
    runtime._wire_being_stack()
    for spawn in scenario.player_spawns:
        try:
            runtime._aux_being_provisioning.ensure_attached(
                PlayerId(int(spawn.player_id))
            )
        except Exception as exc:
            raise RuntimeError(
                f"player_id={spawn.player_id} の Being を用意できず、入るときの紹介を"
                "渡せない"
            ) from exc
    # PR #451 (PR 6/6): LLM 経路は _build_short_term_memory の ctor 注入で
    # 既に揃っている。旧 _wire_short_term_llm_services による setter 後注入は廃止
    # (setter 呼び忘れ silent failure を構造で排除)。

    runtime._wire_being_stack()
    from ai_rpg_world.application.observation.being_contract import (
        environment_entry_for_player,
    )

    for spawn in scenario.player_spawns:
        player_id = PlayerId(int(spawn.player_id))
        player_acquaintances.receive_entry(
            player_id, environment_entry_for_player(scenario, player_id)
        )
    _record_meetings_at_spawn(scenario, player_acquaintances)
    from ai_rpg_world.application.llm.services.executors.being_episode_index_revision_tool_executor import (
        BeingEpisodeIndexRevisionToolExecutor,
    )
    from ai_rpg_world.application.llm.services.executors.being_episode_recall_tool_executor import (
        BeingEpisodeRecallToolExecutor,
    )

    runtime._being_episode_recall_tool_executor = BeingEpisodeRecallToolExecutor(
        repository=runtime._being_episode_store,
        turn_reader=memory_turn_clock,
        max_handles=config.being_episode_recall_max_handles,
        trace_recorder_provider=lambda: runtime._trace_recorder,
        current_tick_provider=lambda: runtime.current_tick(),
    )
    runtime._being_episode_index_revision_tool_executor = (
        BeingEpisodeIndexRevisionToolExecutor(
            repository=runtime._being_episode_store,
            turn_reader=memory_turn_clock,
            trace_recorder_provider=lambda: runtime._trace_recorder,
            current_tick_provider=lambda: runtime.current_tick(),
        )
    )
    runtime._player_episode_writing = _build_player_episode_writing(
        config,
        runtime=runtime,
        turn_reader=memory_turn_clock,
        persona_of=_build_persona_resolver(
            scenario=scenario,
            world_character=world_character,
            persona_block=persona_block,
        ),
    )

    # disabled_tools の名前が実在するかを、ここで確かめる。
    #
    # 判定自体は get_tool_definitions が持っているが、それを待つと
    # presentation 層の起動時検査まで遅れる。**シナリオの書き間違いは
    # シナリオを読んだ直後に落としたい。** run を 1 本流し終えてから
    # 「無効化したつもりが出たままだった」と気付くのが最悪の形。
    from ai_rpg_world.application.world_runtime.public_sns_wiring import wire_public_sns
    wire_public_sns(runtime)
    runtime._validate_disabled_tool_names()
    runtime._validate_action_argument_classification_at_startup()
    runtime._validate_prompt_argument_contract_at_startup()
    episode_index_shown, episode_recall_offered = (
        runtime._episode_index_parts_named_in_system_prompt()
    )
    runtime._world_llm_system_prompt = _world_system_prompt(
        persona_block,
        episode_index_shown=episode_index_shown,
        episode_recall_offered=episode_recall_offered,
    )
    runtime._world_llm_system_prompts_by_player_id = {
        player_id: _world_system_prompt(
            persona,
            episode_index_shown=episode_index_shown,
            episode_recall_offered=episode_recall_offered,
        )
        for player_id, persona in personas_by_player_id.items()
    }
    return runtime


# PR #451 (PR 6/6): _wire_short_term_llm_services は廃止。
# 旧来は ctor で空殻 (summary_service=None) を作り、後で setter 注入する 2 段階
# 構築だったが、setter 呼び忘れで silent failure を量産 (PR #444 の実害)。
# 本 PR で _build_short_term_memory に統合し ctor 一発注入に変更したため、
# 後注入用のこの helper は不要になった。
