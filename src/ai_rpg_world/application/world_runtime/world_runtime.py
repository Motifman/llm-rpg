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
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, ClassVar, Dict, FrozenSet, List, Optional, Tuple

logger = logging.getLogger(__name__)

from ai_rpg_world.domain.item.read_model.item_spec_read_model import ItemSpecReadModel
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
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
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.application.world_graph.spot_graph_current_state_builder import (
    SpotGraphCurrentStateBuilder,
)
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphInventoryItemEntry,
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
from ai_rpg_world.application.llm.contracts.dtos import (
    LlmCommandResultDto,
    LlmUiContextDto,
    ToolDefinitionDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import get_spot_graph_specs
from ai_rpg_world.application.llm.services.tool_catalog.subjective_action import (
    with_expected_result_schema,
    GOAL_OUTCOME_ABANDONED,
    GOAL_OUTCOME_ACHIEVED,
    with_goal_outcome_schema,
    with_goal_update_schema,
)
from ai_rpg_world.application.llm.tool_constants import (
    TOOL_NAME_SPOT_GRAPH_DROP_ITEM,
    TOOL_NAME_SPOT_GRAPH_EXPLORE,
    TOOL_NAME_SPOT_GRAPH_INTERACT,
    TOOL_NAME_SPOT_GRAPH_PICKUP_ITEM,
    TOOL_NAME_SPOT_GRAPH_TRAVEL_TO,
    TOOL_NAME_SPOT_GRAPH_WAIT,
)
from ai_rpg_world.application.llm.services.tool_catalog.memory import get_memory_specs
from ai_rpg_world.application.llm.services.sliding_window_memory import DefaultSlidingWindowMemory
from ai_rpg_world.application.llm.contracts.interfaces import ISlidingWindowMemory
from ai_rpg_world.application.llm.services.action_result_store import DefaultActionResultStore
from ai_rpg_world.application.llm.services.action_result_recorder import ActionResultRecorder
from ai_rpg_world.application.llm.services.prediction_context_ledger import (
    PredictionContextLedger,
)
from ai_rpg_world.application.llm.services.context_format_strategy import (
    SectionBasedContextFormatStrategy,
)
from ai_rpg_world.application.llm.services.recent_events_formatter import DefaultRecentEventsFormatter
from ai_rpg_world.application.llm.services.subjective_time import utc_now as _subjective_time_utc_now
from ai_rpg_world.application.llm.services.in_memory_todo_store import InMemoryTodoStore
from ai_rpg_world.application.llm.services.executors.todo_executor import TodoToolExecutor
from ai_rpg_world.application.llm.services.world_llm_prompt import (
    CharacterPromptInput,
    build_world_system_prompt,
    build_persona_block_from_character,
    safe_world_intro_text,
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
from ai_rpg_world.infrastructure.unit_of_work.in_memory_unit_of_work import (
    InMemoryUnitOfWork,
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


@dataclass
class WorldRuntime:
    """LLM エージェントが世界で生きる汎用ランタイム（全てインメモリ）。"""

    scenario: ScenarioLoadResult
    _spot_graph_repo: InMemorySpotGraphRepository
    _spot_interior_repo: InMemorySpotInteriorRepository
    _player_status_repo: InMemoryPlayerStatusRepository
    _player_inventory_repo: InMemoryPlayerInventoryRepository
    _item_repo: InMemoryItemRepository
    _item_spec_repo: InMemoryItemSpecRepository
    _world_flag_state: MutableWorldFlagState
    _exploration_progress: InMemorySpotExplorationProgressStore
    _movement_service: SpotGraphMovementApplicationService
    _interaction_service: SpotInteractionApplicationService
    _exploration_service: SpotExplorationApplicationService
    _item_transfer_service: SpotGraphItemTransferService
    _state_builder: SpotGraphCurrentStateBuilder
    _game_end_evaluator: GameEndConditionEvaluator
    _formatter: SpotGraphCurrentStateFormatter
    _ui_context_builder: SpotGraphUiContextBuilder
    _obs_pipeline: ObservationPipeline
    _obs_buffer: DefaultObservationContextBuffer
    _sliding_window: DefaultSlidingWindowMemory
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
    # 構築時は None、runtime 構築後に world_runtime が代入する。
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
    # P6 (目的の見直し): GOAL_REVISION_ENABLED の解決結果と、goal_update を
    # 反映する applier。flag OFF / goal store 無しなら applier は None。
    _goal_revision_enabled: bool = field(default=False, repr=False)
    _goal_revision_applier: Optional[Any] = field(default=None, repr=False)
    # Issue #526 後続: LLM が「思い出そう」と意志して過去 episode を呼び戻す
    # ``memory_recall_episodes`` tool の executor。``_wire_auxiliary_tool_stack``
    # 時に episodic_stack が wire されていれば構築。OFF (= 構築されない) なら
    # tool 定義もリストに出さず、run_llm_auxiliary_tool でも未対応扱い。
    # 型は ``Optional["EpisodicMemoryRecallToolExecutor"]`` だが circular import
    # 回避のため lazy import + ``Any`` 注釈にしている (= 既存の lazy executor
    # 配線と同じパターン)。
    _memory_recall_tool_executor: Optional[Any] = field(default=None, repr=False)
    # PR-D: afterglow handle から本文を引き戻す ``memory_recall_by_handle``
    # tool の executor。slot / afterglow / episode_store + 現 tick provider を
    # 統合する必要があるため、``_wire_auxiliary_tool_stack`` で構築。
    # 構築されなければ tool 定義もリストに出さず、handler も未対応扱い。
    _memory_recall_by_handle_tool_executor: Optional[Any] = field(default=None, repr=False)
    # シナリオ実行 trace の recorder。未設定なら NullTraceRecorder にフォールバック
    # (Phase 1d 配線)。
    _trace_recorder: Any = field(default=None, repr=False)
    # B-4: LLM に提示するツールセットの mode。``True`` (既定) なら TODO 系も
    # 含む従来構成、``False`` なら純スポットグラフ + speech のみ。
    # Issue #155 (TODO 設計の再評価) の判断材料を取るための比較実験用。
    _include_todo_tools: bool = field(default=True, repr=False)
    # Prediction (#526 v0): 行動前の予測 expected_result を core action tool の
    # schema に露出する policy。``"off"`` (露出せず=既定/挙動不変) | ``"optional"``
    # (schema に出すが必須にしない) | ``"required"`` (毎ターン必須)。factory が
    # ResolvedLlmRuntimeConfig.expected_result_policy から設定する。
    _expected_result_policy: str = field(default="off", repr=False)
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
        tick = self._simulation_service.tick()
        self._tick = tick.value
        # #356 後続: 日が変わったら腐敗バッファを flush して 1 件にまとめる。
        # buffer は _append_food_spoiled_batch_observation で積まれる。
        # tick が 0 base なので day = tick // ticks_per_day。
        pending_day = getattr(self, "_pending_spoiled_day", None)
        if pending_day is not None:
            ticks_per_day = self._ticks_per_day_or_default()
            current_day = tick.value // max(1, ticks_per_day)
            if pending_day != current_day:
                self._flush_pending_food_spoiled()
        return tick.value

    def set_trace_recorder(self, recorder: Any) -> None:
        """シナリオ実行 trace の recorder を後から差し込む (Phase 1d 配線)。

        ``create_session`` などで world_runtime を構築した後に
        外側から trace を有効化する用途。memo executor は lazy 構築なので
        既に作成済みでもこのフィールドが反映される。
        """
        self._trace_recorder = recorder
        # 既に memo executor が wire 済みなら作り直してから recorder を行き渡らせる
        if self._todo_tool_executor is not None:
            self._todo_tool_executor = None
            self._wire_auxiliary_tool_stack()
        # PR #439: RollingSummaryShortTermMemory を使っている場合、L4 / L5 trace を
        # 出せるようにここで provider を注入する (sliding_window 構築時点では
        # _trace_recorder が確定していなかった silent failure 対策)。
        # 既存の sliding_window 実装 (DefaultSlidingWindowMemory) は setter を持たない
        # ので getattr で安全に skip する。
        set_recorder = getattr(self._sliding_window, "set_trace_recorder_provider", None)
        if callable(set_recorder):
            set_recorder(lambda: self._trace_recorder)
        set_tick = getattr(self._sliding_window, "set_current_tick_provider", None)
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
        names = [d.name for d in self.get_tool_definitions()]
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
        return self._ui_context_builder.build(base_text, dto)

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
        )

    def get_tool_definitions(self) -> List[ToolDefinitionDto]:
        """LLM に渡されるツール定義（OpenAI tools 形式）を返す。

        ``_include_todo_tools=False`` の場合は TODO 系 (todo_add / todo_list /
        todo_complete) を除外し、spot_graph_* + speech (say / whisper) のみ
        を返す。LLM が「TODO 操作の連打」に逃げない条件で挙動を比較するため
        の純スポットグラフモード (B-4 / Issue #155 の判断材料)。

        Issue #526 後続: episodic_stack が wire されていれば
        ``memory_recall_episodes`` (= LLM が能動的に過去 episode を呼び戻す
        tool) も併せて含める。``_episodic_stack=None`` 時は出さない (= 学習
        パイプラインが無い実験 run と区別する)。
        """
        spot = [
            self._with_goal_update_if_enabled(
                self._with_expected_result_if_enabled(defn)
            )
            for defn, _ in get_spot_graph_specs()
        ]
        if not self._include_todo_tools:
            return spot
        # Issue #526 後続: tool を expose するタイミングで auxiliary stack を
        # 確実に wire しておく (= 「定義は出すが handler が無い」状態を防ぐ)。
        # idempotent なので毎回呼んで OK。
        if self._episodic_stack is not None:
            self._wire_auxiliary_tool_stack()
        episodic_recall_enabled = self._memory_recall_tool_executor is not None
        recall_by_handle_enabled = (
            self._memory_recall_by_handle_tool_executor is not None
        )
        memo = [
            defn
            for defn, _ in get_memory_specs(
                todo_enabled=True,
                episodic_recall_enabled=episodic_recall_enabled,
                recall_by_handle_enabled=recall_by_handle_enabled,
            )
        ]
        return spot + memo

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

        ``PREDICTION_CONTEXT_ID_ENABLED`` env で default OFF
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
            resolve_prediction_context_id_enabled,
        )

        enabled = resolve_prediction_context_id_enabled()
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
        success: bool = True,
        error_code: Optional[str] = None,
        scene_boundary: bool = False,
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

        ``expected_result`` / ``intention`` / ``emotion_hint``: LLM が行動前に
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
        recorder.record(
            player_id,
            action_summary=action_summary,
            result_summary=result_summary,
            occurred_at=datetime.now(timezone.utc),
            tool_name=tool_name,
            success=success,
            error_code=error_code,
            scene_boundary=scene_boundary,
            expected_result=expected_result,
            intention=intention,
            emotion_hint=emotion_hint,
            # Issue #311 後続: bucket 内 actions の tick 差で TEMPORAL_GAP 判定するため
            occurred_tick=self.current_tick(),
            episodic_stack=self._episodic_stack,
        )

    def _drain_buffer_to_sliding_window(self, player_id: PlayerId) -> List[ObservationEntry]:
        """観測バッファをスライディングウィンドウに移す。溢れた観測を返す。"""
        drained = self._obs_buffer.drain(player_id)
        if not drained:
            return []
        return self._sliding_window.append_all(player_id, drained)

    def _wire_auxiliary_tool_stack(self) -> None:
        """TODO ツール実行器を遅延初期化する。

        Phase 3 Step 3a-3: memo は being_id 経路必須なので Resolver+WorldId を
        ここで構築・注入する。WorldRuntime は独自経路で Being を持っていない
        ため、ローカル BeingRepository + Resolver を毎回作って provision する。
        run_llm_auxiliary_tool が呼ばれる前に必ず Being attach を済ませる。

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
        from ai_rpg_world.domain.being.service.being_attachment_resolver import (
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
            sliding_window=self._sliding_window,
            action_result_store=self._action_result_store,
            current_tick_provider=self.current_tick,
            trace_recorder=self._trace_recorder,
            being_attachment_resolver=self._aux_being_resolver,
            default_world_id=self._aux_being_default_world_id,
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
        """Issue #526 後続: memory_recall_episodes tool を idempotent に組み立てる。

        episodic_stack が無いと episode store / noun_matcher にアクセス
        できないため、その場合は executor を作らない (= tool は LLM 側
        に出さない)。``_aux_being_resolver`` / ``_aux_being_default_world_id``
        は ``_wire_auxiliary_tool_stack`` 内で先に初期化される前提。

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
                being_attachment_resolver=self._aux_being_resolver,
                default_world_id=self._aux_being_default_world_id,
                noun_matcher=self._episodic_stack.noun_matcher,
                time_provider=utc_now,
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
                    being_attachment_resolver=self._aux_being_resolver,
                    default_world_id=self._aux_being_default_world_id,
                    current_tick_provider=lambda: self.current_tick(),
                )
            )

    @property
    def aux_being_resolver(self):
        """Phase 3 Step 3a-3: presentation 層から MemoCompletionHintService 等に
        渡すための ``_aux_being_resolver`` 公開。``_wire_auxiliary_tool_stack``
        を呼んでいないと None。
        """
        return getattr(self, "_aux_being_resolver", None)

    @property
    def aux_being_default_world_id(self):
        """Phase 3 Step 3a-3: aux Being の default WorldId 公開アクセサ。"""
        return getattr(self, "_aux_being_default_world_id", None)

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
        # idempotent: 既に attach 済なら何もしない
        self._aux_being_provisioning.ensure_attached(player_id)
        assert self._todo_tool_executor is not None
        handlers: Dict[str, Any] = dict(self._todo_tool_executor.get_handlers())
        if self._memory_recall_tool_executor is not None:
            recall_handlers = self._memory_recall_tool_executor.get_handlers()
            # サイレント上書き防止: 将来 executor が増えたとき同名 tool が
            # 出ると後勝ちで挙動が変わるため、明示的に衝突を検出する。
            overlap = handlers.keys() & recall_handlers.keys()
            if overlap:
                raise RuntimeError(
                    f"tool handler name collision in aux stack: {sorted(overlap)}"
                )
            handlers.update(recall_handlers)
        # PR-D: recall_by_handle も同じ aux 経路で動かす。
        if self._memory_recall_by_handle_tool_executor is not None:
            by_handle_handlers = (
                self._memory_recall_by_handle_tool_executor.get_handlers()
            )
            overlap = handlers.keys() & by_handle_handlers.keys()
            if overlap:
                raise RuntimeError(
                    f"tool handler name collision in aux stack: {sorted(overlap)}"
                )
            handlers.update(by_handle_handlers)
        handler = handlers.get(name)
        if handler is None:
            return LlmCommandResultDto(
                success=False,
                message=f"未対応のツールです: {name}",
                error_code="UNSUPPORTED_TOOL",
            )
        return handler(int(player_id), arguments)

    def _format_inventory_evidence(self, player_id: PlayerId) -> str:
        inv = self._player_inventory_repo.find_by_id(player_id)
        if inv is None:
            return "（なし）"
        lines: List[str] = []
        from ai_rpg_world.domain.player.value_object.slot_id import SlotId

        for slot_idx in range(inv._max_slots):
            iid = inv.get_item_instance_id_by_slot(SlotId(slot_idx))
            if iid is None:
                continue
            item = self._item_repo.find_by_id(iid)
            if item is None:
                continue
            name = item.item_spec.name
            desc = (item.item_spec.description or "").strip()
            if desc:
                lines.append(f"- {name}（{desc[:120]}…）" if len(desc) > 120 else f"- {name}（{desc}）")
            else:
                lines.append(f"- {name}")
        return "\n".join(lines) if lines else "（なし）"

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

    def _resolve_scenario_llm_objective_text(self) -> str:
        """``scenario.metadata.llm_objective_text`` を解決し、未設定なら ValueError。

        prompt の objective section に直接埋め込む文。fallback を意図的に持たない:
        - scenario A の objective を scenario B で再利用すると LLM が別ゲームを
          始めてしまう (= cross-scenario silent failure)
        - シナリオ作者に「LLM ゴール文」を明示的に書かせる強制力
        """
        text = (self.scenario.metadata.llm_objective_text or "").strip()
        if not text:
            scenario_id = self.scenario.metadata.id or "<unknown>"
            raise ValueError(
                f"scenario {scenario_id!r} has empty metadata.llm_objective_text; "
                "LLM の objective section に埋め込む勝利条件文を scenario JSON の "
                "metadata.llm_objective_text に追加してください "
                "(例: \"- 山頂の狼煙台で火を上げ、救助船 (4日目/6日目/7日目) を待つ\")"
            )
        return text

    def _resolve_objective_via_goal_store(
        self, player_id: PlayerId, fallback_text: str
    ) -> str:
        """P5 (目的層 G1): goal store の active 目的を【現在の目的】に描画する。

        遅延 seed: その being にまだ目的が無ければ、シナリオ目的文を
        ``locked=True / origin=scenario`` で 1 度だけ seed する (以後 active を
        描画)。locked 初期値なので描画結果は ``fallback_text`` と同一 = 既存
        シナリオの挙動不変。store 未構築・being 未解決なら安全に fallback_text。
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
                locked=True,
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
            return self._resolve_scenario_llm_objective_text()
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
    # Issue #526 後続 (主観時間 v0): 「直近の出来事」の各行に「昨日 /
    # 数分前」等のラベルを付ける。time_provider は wall-clock の
    # datetime.now (= observation.occurred_at と同じ時間軸)。
    _recent_events_formatter: ClassVar[DefaultRecentEventsFormatter] = (
        DefaultRecentEventsFormatter(time_provider=_subjective_time_utc_now)
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
            sliding_window_memory=self._sliding_window,
            action_result_store=self._action_result_store,
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
            objective_text_provider=lambda pid: self._resolve_objective_via_goal_store(
                pid, resolved_objective_text
            ),
            inventory_text_provider=lambda pid: self._format_inventory_evidence(pid),
            memo_store=self._todo_store,
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
            # #526 後続 (habituation 配線漏れ修正): being_id 解決のため
            # ``being_attachment_resolver`` と ``default_world_id`` を渡す。
            # これらが None のままだと ``_resolve_being_id`` が常に None を
            # 返し、慣化 (PR #565) / memo / recall_buffer / reinterpretation
            # journal lookup の being_id 経路が silent skip されていた。
            # passive_recall service 側 (build_episodic_stack 経由) には
            # 既に渡している (world_episodic_wiring 経路) が、prompt_builder
            # 側の ctor だけ落ちていた。
            # ``_aux_being_resolver`` は ``_wire_auxiliary_tool_stack()`` で
            # 初期化される lazy attribute なので、未配線時 (= 古いテスト
            # 経路) でも graceful に None を渡せるよう getattr で守る。
            being_attachment_resolver=getattr(
                self, "_aux_being_resolver", None
            ),
            default_world_id=getattr(
                self, "_aux_being_default_world_id", None
            ),
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

    def build_full_prompt(self, player_id: PlayerId) -> dict:
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

        builder = self._get_or_build_default_prompt_builder()
        result = builder.build(player_id)

        # tool_runtime_context は world_runtime 独自の build_llm_context 経由で取得
        ctx = self.build_llm_context(player_id)

        return {
            "messages": result["messages"],
            "tools": [d.name for d in self.get_tool_definitions()],
            "tool_runtime_context": ctx.tool_runtime_context,
            # U1: このターンに発行された prediction_context_id をそのまま
            # 露出する (実際の consume は _record_action_result → ledger 経由
            # で player_id をキーに行われるため、呼び出し側がこの値を渡す
            # 必要は無いが、後続 PR のデバッグ・trace 突き合わせ用に残す)。
            "prediction_context_id": result.get("prediction_context_id"),
        }

    # ── アクション実行 ──

    @staticmethod
    def _interaction_action_label_ja(action_name: str) -> str:
        key = (action_name or "").strip().lower()
        known = {
            "open": "開く",
            "close": "閉じる",
            "examine": "調べる",
            "search": "探す",
            "read": "読む",
            "use": "使う",
            "take": "取る",
            "push": "押す",
            "pull": "引く",
        }
        return known.get(key, action_name or "操作")

    def _object_display_name_at_player_spot(
        self, player_id: PlayerId, object_str_id: str,
    ) -> str:
        try:
            obj_int = self.id_mapper.get_int("object", object_str_id)
            oid = SpotObjectId.create(obj_int)
            graph = self._spot_graph_repo.find_graph()
            eid = EntityId.create(int(player_id))
            spot_id = graph.get_entity_spot(eid)
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
        expected_result: Optional[str] = None,
        intention: Optional[str] = None,
        emotion_hint: Optional[str] = None,
    ) -> SpotInteractionResultDto:
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import SpotObjectInteractedEvent
        obj_int = self.id_mapper.get_int("object", object_str_id)
        obj_id = SpotObjectId.create(obj_int)
        graph = self._spot_graph_repo.find_graph()
        eid = EntityId.create(int(player_id))
        spot_id = graph.get_entity_spot(eid)
        obj_label = self._object_display_name_at_player_spot(player_id, object_str_id)
        action_ja = self._interaction_action_label_ja(action_name)
        result = self._interaction_service.execute_interaction(
            player_id, obj_id, action_name,
        )
        result_text = "; ".join(result.messages) if result.messages else "完了"
        graph = self._spot_graph_repo.find_graph()
        graph.add_event(SpotObjectInteractedEvent.create(
            aggregate_id=graph._graph_id,
            aggregate_type="SpotGraphAggregate",
            entity_id=eid,
            spot_id=spot_id,
            object_id=obj_id,
            action_name=action_name,
            result_message=result_text,
        ))
        self._process_graph_events()
        # SpotInteractionResultDto は現状 success フラグを持たない (messages から
        # しか判定できない)。fail 検出経路がドメイン側に出来るまで暫定で True 固定。
        self._record_action_result(
            player_id,
            f"「{obj_label}」に対して{action_ja}を行った",
            result_text,
            tool_name=TOOL_NAME_SPOT_GRAPH_INTERACT,
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

    def do_listen(self, player_id: PlayerId) -> int:
        """「耳を澄ます」: 自 spot + 隣接 spot の環境音観測を投入する。

        ``SpotGraphAggregate.emit_listen_carefully`` で
        ``SpotSoundHeardEvent`` を発火し、観測パイプラインで recipient
        strategy がプレイヤー本人にだけ届ける (formatter が prose を組む)。

        Returns:
            **本 listen 呼び出しで新たに発火した** event 数 (= 観測が届いた
            spot の数)。「何も聞こえない」ケース (全 spot SILENT または
            減衰しきり) は 0。

        Note:
            graph 集約の event queue は本メソッド呼び出し前にも他経路
            (tick 内の他 stage / 並行 do_* 呼び出し等) が積んだ stale event
            を含みうる。``emit_listen_carefully`` 前後で長さを snapshot して
            **差分** をカウントすることで、メッセージ上の「N 箇所から」が
            実際の listen 結果と一致するようにする (review HIGH-1 反映)。
        """
        graph = self._spot_graph_repo.find_graph()
        eid = EntityId.create(int(player_id))
        pre_count = len(list(graph.get_events()))
        # `add_event` は graph 集約内に積むだけで保存はしない。
        # `_process_graph_events` が `get_events` で取り出して observation
        # pipeline に流す。
        graph.emit_listen_carefully(eid)
        post_count = len(list(graph.get_events()))
        new_event_count = max(0, post_count - pre_count)
        # _process_graph_events 内部で clear するので、ここでは再取得しない。
        self._process_graph_events()
        return new_event_count

    def do_explore(
        self,
        player_id: PlayerId,
        *,
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
            scene_boundary=True,
            expected_result=expected_result,
            intention=intention,
            emotion_hint=emotion_hint,
        )

    def do_wait(
        self,
        player_id: PlayerId,
        reason: str = "",
        *,
        expected_result: Optional[str] = None,
        intention: Optional[str] = None,
        emotion_hint: Optional[str] = None,
    ) -> int:
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
        だけを記録する。world tick の進行は外側 driver loop に任せる。
        返り値は現在 tick (進めていない) を返す互換のため。
        """
        tick = self.current_tick()
        r = (reason or "").strip()
        if r:
            self._record_action_result(
                player_id,
                f"待機した（理由: {r}）",
                f"今ターンは行動を控えた（tick={tick}）",
                tool_name=TOOL_NAME_SPOT_GRAPH_WAIT,
                expected_result=expected_result,
                intention=intention,
                emotion_hint=emotion_hint,
            )
        else:
            self._record_action_result(
                player_id,
                "短く待機した",
                f"今ターンは行動を控えた（tick={tick}）",
                tool_name=TOOL_NAME_SPOT_GRAPH_WAIT,
                expected_result=expected_result,
                intention=intention,
                emotion_hint=emotion_hint,
            )
        return tick

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

    def _scenario_event_recipients(self, event: ScenarioEventDef) -> List[PlayerId]:
        if event.recipients == "players_at_spot" and event.target_spot_id is not None:
            graph = self._spot_graph_repo.find_graph()
            presence = graph.presence_at(SpotId.create(event.target_spot_id))
            return [PlayerId(int(eid)) for eid in presence.present_entity_ids]
        return self.get_player_ids()

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
        # Phase E-3c: scenario が outcome_resolution_config を宣言している
        # シナリオでは「all_resolved」(全員 outcome 確定) を game end の唯一の
        # 終了条件にする。集団 WIN/LOSE の概念は廃止 (per-player outcome の
        # snapshot だけが結果)。
        # outcome_resolution が無いシナリオ (v1 等) は従来の集団判定経路を維持。
        if (
            self.scenario.outcome_resolution_config is not None
            and self._player_outcome_registry is not None
        ):
            return self._check_game_end_outcome_mode()
        return self._check_game_end_collective_mode()

    def _check_game_end_outcome_mode(self) -> GameEndResult:
        """Phase E-3c: per-player outcome モードでの終了判定。

        全プレイヤーが RESCUED/DEAD/STRANDED のいずれかに確定したら end。
        `result` は集団 WIN/LOSE を意図的に None にし、`player_outcomes` で
        個別結果を返す。集団勝敗の概念は v2 シナリオで廃止。
        """
        registry = self._player_outcome_registry
        if not registry.all_resolved():
            return GameEndResult(
                is_ended=False, result=None,
                reason="未確定プレイヤーあり (per-player outcome モード)",
            )
        snapshot = registry.snapshot()
        return GameEndResult(
            is_ended=True,
            result=None,
            reason=f"全 {len(snapshot)} プレイヤーの outcome が確定",
            player_outcomes=snapshot,
        )

    def _check_game_end_collective_mode(self) -> GameEndResult:
        """v1 / 既存シナリオ用の集団 win/lose 判定。挙動は従来通り。"""
        graph = self._spot_graph_repo.find_graph()
        flags = self._world_flag_state.as_frozen_set()
        player_ids = self.get_player_ids()
        from ai_rpg_world.domain.common.value_object import WorldTick
        tick = WorldTick(self._tick)
        for wc in self.scenario.win_conditions:
            result = self._game_end_evaluator.evaluate(graph, wc, flags, player_ids, tick)
            if result.is_ended:
                return result
        for lc in self.scenario.lose_conditions:
            result = self._game_end_evaluator.evaluate(graph, lc, flags, player_ids, tick)
            if result.is_ended:
                return result
        return GameEndResult(is_ended=False, result=None, reason="ゲーム続行中")

    def get_player_spot_name(self, player_id: PlayerId) -> str:
        graph = self._spot_graph_repo.find_graph()
        eid = EntityId.create(int(player_id))
        spot_id = graph.get_entity_spot(eid)
        return graph.get_spot(spot_id).name

    def get_player_spot_id(self, player_id: PlayerId) -> Optional[str]:
        """プレイヤーが現在いる spot の生 ID 文字列を返す (見つからなければ None)。

        trace の ``position_change`` event payload に乗せる用途。
        例: スポット間移動の trail 描画。
        """
        try:
            graph = self._spot_graph_repo.find_graph()
            eid = EntityId.create(int(player_id))
            spot_id = graph.get_entity_spot(eid)
        except Exception:
            return None
        if spot_id is None:
            return None
        # SpotId は value_object なので value を取り出す
        value = getattr(spot_id, "value", None)
        if value is None:
            return str(spot_id)
        return str(value)


def _world_llm_ssot_enabled_from_env() -> bool:
    """環境変数 ESCAPE_LLM_SSOT が 1/true/yes/on のいずれかなら SSoT を有効にする。"""
    v = os.environ.get("ESCAPE_LLM_SSOT", "").strip().lower()
    return v in ("1", "true", "yes", "on")


_ENV_LLM_TOOL_MODE = "LLM_TOOL_MODE"
_LLM_TOOL_MODE_DEFAULT = "default"
_LLM_TOOL_MODE_PURE_SPOT_GRAPH = "pure_spot_graph"
# TODO(#155): 「TODO 系の有無」以外の軸が増えたら bool 戻り値ではなく
# ``_resolve_tool_mode_from_env() -> str`` に書き直す。例: "no_memory" や
# "minimal_combat" のような細かい mode が要る場合。binary で済む間は単純化
# を優先。
_VALID_LLM_TOOL_MODES = frozenset(
    {_LLM_TOOL_MODE_DEFAULT, _LLM_TOOL_MODE_PURE_SPOT_GRAPH}
)


def _include_todo_tools_from_env() -> bool:
    """環境変数 ``LLM_TOOL_MODE`` を解釈し TODO 系ツールを含めるかを返す。

    - ``default`` (既定 / 未設定): TODO 系を含める従来構成
    - ``pure_spot_graph``: TODO 系を除外、spot_graph_* + speech のみ
    - 未知の値: warning ログを残して既定 (TODO 含む) にフォールバック

    システムプロンプト側には mode のヒントを意図的に伝えない (B-4 設計判断)。
    LLM が「TODO 系が無い環境でどう動くか」を観察するための実験なので、
    プロンプトで「TODO ツールは使えません」と教えると測定が汚染される。
    現代のツール呼び出しモデルは tools リストに無いツールを呼ばないという
    前提に依存している。
    """
    raw = os.environ.get(_ENV_LLM_TOOL_MODE, "").strip().lower()
    if not raw:
        return True  # 既定は TODO 含む
    if raw not in _VALID_LLM_TOOL_MODES:
        logger.warning(
            "Unknown %s=%r; valid values are %s. Falling back to %r.",
            _ENV_LLM_TOOL_MODE,
            raw,
            sorted(_VALID_LLM_TOOL_MODES),
            _LLM_TOOL_MODE_DEFAULT,
        )
        return True
    return raw != _LLM_TOOL_MODE_PURE_SPOT_GRAPH


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
) -> ISlidingWindowMemory:
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
      2. ``RollingSummaryShortTermMemory(summary_service=X, long_summary_service=Y,
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
        return DefaultSlidingWindowMemory()

    # rolling_summary 経路: LLM 経路を **構築時点で揃える**
    from ai_rpg_world.application.llm.services.rolling_summary_short_term_memory import (
        RollingSummaryShortTermMemory,
    )
    from ai_rpg_world.application.llm.services.short_term_memory_long_summary_service import (
        ShortTermMemoryLongSummaryService,
    )
    from ai_rpg_world.application.llm.services.short_term_memory_summary_service import (
        ShortTermMemorySummaryService,
    )
    from ai_rpg_world.application.llm.wiring._llm_client_factory import (
        create_llm_client_from_env,
    )
    from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient

    summary_service = None
    long_summary_service = None
    persona_resolver = None
    if cfg.llm_client_kind == "litellm":
        try:
            client = create_llm_client_from_env()
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

    return RollingSummaryShortTermMemory(
        summary_service=summary_service,
        long_summary_service=long_summary_service,
        persona_resolver=persona_resolver,
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
            ``ResolvedLlmRuntimeConfig.from_env()`` で env から 1 度だけ resolve。
            entrypoint (run_scenario_experiment 等) で既に from_env() 済みの cfg を
            渡せば、env を 2 度読まず確実に同じ値を共有する。**run_start trace と
            実 wiring の同一性を構造で保証する**ための引数。
    """
    # PR #448: env を読むのはここ 1 回だけ (= 単一窓口)。引数 cfg が来ていれば
    # それを使うが、来ていなければ from_env() で構築する (= 後方互換)。
    from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
        ResolvedLlmRuntimeConfig,
    )

    if config is None:
        config = ResolvedLlmRuntimeConfig.from_env()

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
    _has_goal = bool(
        scenario.win_conditions
        or scenario.lose_conditions
        or scenario.outcome_resolution_config is not None
    )
    safe_intro = safe_world_intro_text(scenario.metadata, has_goal=_has_goal)
    participants = _other_explorer_names_for_world_system_prompt(
        scenario.player_spawns, world_character
    )
    system_prompt_text = build_world_system_prompt(
        world_title=scenario.metadata.title,
        persona_block=persona_block,
        safe_intro=safe_intro,
        participant_names=participants,
        enable_string_seed_of_thought=_world_llm_ssot_enabled_from_env(),
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
            # この spawn から見た「他者」名リスト
            other_names = tuple(s.name for s in scenario.player_spawns if s is not spawn)
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
            system_prompts_by_player_id[int(spawn.player_id)] = (
                build_world_system_prompt(
                    world_title=scenario.metadata.title,
                    persona_block=this_persona,
                    safe_intro=safe_intro,
                    participant_names=other_names,
                    enable_string_seed_of_thought=_world_llm_ssot_enabled_from_env(),
                    expected_result_policy=config.expected_result_policy,
                    has_goal=_has_goal,
                )
            )

    data_store = InMemoryDataStore()

    spot_graph_repo = InMemorySpotGraphRepository(scenario.graph)

    spot_interior_repo = InMemorySpotInteriorRepository()
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
        )
        item_spec_repo.save(spec)

    player_status_repo = InMemoryPlayerStatusRepository(data_store)
    player_inventory_repo = InMemoryPlayerInventoryRepository(data_store)

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
            gold=Gold(0),
            hp=Hp(value=100, max_hp=100),
            mp=Mp(value=50, max_mp=50),
            stamina=Stamina(value=100, max_stamina=100),
            navigation_state=PlayerNavigationState.from_parts(
                current_spot_id=spawn.spawn_spot_id,
                current_coordinate=Coordinate(0, 0, 0),
            ),
            spot_navigation_state=PlayerSpotNavigationState.at_rest(spawn.spawn_spot_id),
        )
        player_status_repo.save(status)
        player_inventory_repo.save(PlayerInventoryAggregate(player_id=pid))

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
    skill_loadout_repo = InMemorySkillLoadoutRepository()
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

    movement_service = SpotGraphMovementApplicationService(
        spot_graph_repository=spot_graph_repo,
        player_status_repository=player_status_repo,
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
                item_spec_id=ItemSpecId.create(e.item_spec_id),
                weight=e.weight,
                min_quantity=e.min_quantity,
                max_quantity=e.max_quantity,
            )
            for e in lt_def.entries
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
    _effect_service = WorldGraphEffectService(loot_table_repository=loot_table_repo)
    _interaction_domain_service = SpotInteractionService(effect_service=_effect_service)
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
    )
    exploration_service = SpotExplorationApplicationService(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        player_inventory_repository=player_inventory_repo,
        item_repository=item_repo,
        item_spec_repository=item_spec_repo,
        world_flag_state=world_flag_state,
        exploration_progress_store=exploration_progress,
    )
    # spot-graph 世界専用の drop/pickup サービス。
    # tile-map 時代の ItemDroppedFromInventoryDropHandler は
    # physical_map 依存で world_runtime では発火しないため、本サービスが
    # SpotInterior.ground_items に直接書き込んで spot-graph 経路で
    # 拾えるようにする。LLM tool 配線とイベント/観測統合はフォロー
    # アップ PR で扱う。
    item_transfer_service = SpotGraphItemTransferService(
        spot_graph_repository=spot_graph_repo,
        player_inventory_repository=player_inventory_repo,
        spot_interior_repository=spot_interior_repo,
        item_repository=item_repo,
    )
    player_name_map = {spawn.player_id: spawn.name for spawn in scenario.player_spawns}

    def _resolve_entity_name(entity_id: int) -> str:
        return player_name_map.get(entity_id, f"プレイヤー({entity_id})")

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
                # 実験 #29 後続: item_type を持ち回って prompt 側で type タグ
                # 表示できるようにする。ItemType.value は "consumable" 等の
                # 小文字列。enum 経由なので未設定リスクはない。
                item_type_value = item.item_spec.item_type.value
                seen_groups[key] = [name, 0, slot_id, iid.value, item_type_value]
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

    def _build_monster_view_provider_for_runtime(_monster_repo):
        """state_builder に渡す monster_view_provider を遅延構築する小ヘルパ。

        spot_graph_monster_view.build_monster_view_provider を呼ぶだけだが、
        circular import を避けるために関数内 import に寄せた。
        """
        from ai_rpg_world.application.world_graph.spot_graph_monster_view import (
            build_monster_view_provider,
        )
        return build_monster_view_provider(_monster_repo)

    def _resolve_item_spec_name(spec_id_value: int) -> str:
        """item_spec_id → 表示名解決。地面アイテムの prompt 表示などで使う。"""
        from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId as _ISpecId
        spec_union = item_spec_repo.find_by_id(_ISpecId.create(spec_id_value))
        if spec_union is None:
            return ""
        spec = spec_union.to_item_spec() if hasattr(spec_union, "to_item_spec") else spec_union
        return spec.name

    # PR #2 状態異常 surface: 残り tick 表示のため current_tick_provider を
    # state_builder に渡す。time_provider 自体の構築は下方なので、ここでは
    # ホルダー経由で遅延参照する (構築順を入れ替えると他依存が崩れるため)。
    _time_provider_holder: dict[str, Any] = {}

    def _current_tick_provider() -> int:
        tp = _time_provider_holder.get("provider")
        if tp is None:
            return 0
        return tp.get_current_tick().value

    state_builder = SpotGraphCurrentStateBuilder(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        player_status_repository=player_status_repo,
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
    obs_formatter = ObservationFormatter(
        spot_graph_repository=spot_graph_repo,
        monster_repository=monster_repo if scenario.monster_placements else None,
        spot_interior_repository=spot_interior_repo,
    )
    obs_formatter._name_resolver.player_name = lambda pid: player_name_map.get(  # type: ignore[assignment]
        pid.value, f"プレイヤー({pid.value})"
    )

    obs_pipeline = ObservationPipeline(
        resolver=obs_resolver,
        formatter=obs_formatter,
        player_status_repository=player_status_repo,
    )
    obs_buffer = DefaultObservationContextBuffer()
    # PR #451 (PR 6/6): 短期記憶を「全部揃ってから 1 回 build」式に統合。
    # LLM 経路 (summary_service / long_summary_service / persona_resolver) は
    # 旧来 setter で後注入していたが、ctor 注入に統一して呼び忘れ silent failure
    # を構造で排除。trace_recorder / current_tick は runtime instance に依存する
    # ため別経路 (set_trace_recorder) で差し替え (NullObject 経由で安全)。
    sliding_window = _build_short_term_memory(
        config,
        scenario=scenario,
        world_character=world_character,
        persona_block=persona_block,
    )
    action_result_store = DefaultActionResultStore()
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

    # PR4 (Encounter Memory): travel 完了時に actor 本人の spot encounter を
    # 記録する。observation pipeline 経由 (PR3) では他 player の到着が対象に
    # なり、本人の到着は recipient filter で除外されるため、travel_stage の
    # on_arrival callback に独立した hook を入れて補う。
    #
    # ⚠ 制限事項 (= 既知債務、観察者リスト化で解消予定):
    # ``SpotGraphTravelStageService.set_on_arrival`` は単一 callback の上書き
    # API。上位 wiring (= ``presentation/spot_graph_game/runtime_manager.py``
    # の LLM ターン再起床 callback) が後から set すると本 hook は消える。
    # その結果、**ゲームサーバー (= runtime_manager) 経由の実走では本 hook が
    # 発火しない**。world_runtime を直接立てる test / 実験経路でのみ
    # 動作する。観察者リスト (set ではなく append) への refactor は別 PR で
    # 行う。それまでの間、production の travel 到着 encounter は
    # observer-list 化後に有効化される。
    def _record_self_spot_encounter_on_arrival(player_id: PlayerId) -> None:
        try:
            spot_id_raw = runtime.get_player_spot_id(player_id)
            if spot_id_raw is None:
                # player がまだ配置されていない / spot 取得不可。happy-path で
                # 起き得る (= 直後に test や別経路から呼ばれる) ので debug log
                # に留める。
                logger.debug(
                    "encounter on_arrival: spot_id unavailable for player %s",
                    player_id.value,
                )
                return
            spot_int = int(spot_id_raw)
            spot_canonical = scenario.id_mapper.get_str("spot", spot_int)
            encounter_memory.observe(
                player_id,
                EncounterKey.spot(spot_canonical),
                runtime.current_tick(),
            )
        except Exception:
            logger.exception(
                "encounter on_arrival hook failed for player %s",
                player_id.value,
            )

    travel_stage.set_on_arrival(_record_self_spot_encounter_on_arrival)

    scenario_event_progress = InMemorySpotGraphScenarioEventProgressStore()
    # 評価器は scenario_event_stage と reactive_binding_stage で共有する。
    # weather_state_provider を渡すことで WEATHER_IS 条件が解ける。
    # Phase D-1: PROBABILITY 条件評価用の random.Random を注入する。
    # SCENARIO_RANDOM_SEED 環境変数があれば seed 注入で再現性を確保、
    # 無ければ非決定的 (デフォルト random.Random()) で運用する。
    # CI / 実験スクリプトでは seed を固定して同じ rng_sequence を再現できる。
    import os as _os
    import random as _random
    _seed_str = _os.environ.get("SCENARIO_RANDOM_SEED")
    _scenario_random = (
        _random.Random(int(_seed_str)) if _seed_str else _random.Random()
    )
    condition_evaluator = ScenarioConditionEvaluator(
        world_flag_state=world_flag_state,
        spot_interior_repository=spot_interior_repo,
        player_status_repository=player_status_repo,
        player_inventory_repository=player_inventory_repo,
        item_repository=item_repo,
        weather_state_provider=lambda: weather_holder["state"],
        random_source=_scenario_random,
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
    )
    reactive_binding_stage = ReactivePassageBindingStageService(
        bindings=scenario.reactive_passage_bindings,
        spot_graph_repository=spot_graph_repo,
        condition_evaluator=condition_evaluator,
    )
    reactive_object_state_stage = ReactiveObjectStateBindingStageService(
        bindings=scenario.reactive_object_state_bindings,
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        condition_evaluator=condition_evaluator,
    )
    sync_action_registry = SynchronizedActionRegistry(world_flag_state)
    sync_resolver_stage = SynchronizedActionResolverStageService(
        groups=scenario.synchronized_action_groups,
        registry=sync_action_registry,
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        world_flag_state=world_flag_state,
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
    # Phase v2-hunger: outcome_resolution_config 宣言があるシナリオ (= v2 survival)
    # では HUNGER=max のプレイヤーに毎 tick 飢餓ダメージを与える (Minecraft 風)。
    # 既存シナリオ (v1 / 脱出ゲーム) は config を持たないので無影響 (後方互換)。
    # #356 後続: 飢餓ダメージ量を scenario JSON で調整可能にする
    # (`outcome_resolution.starvation_damage_per_tick`)。default 1 で後方互換。
    starvation_dmg = (
        scenario.outcome_resolution_config.starvation_damage_per_tick
        if scenario.outcome_resolution_config is not None
        else 0
    )
    needs_decay_stage = SpotGraphNeedsDecayStageService(
        player_status_repository=player_status_repo,
        starvation_damage_per_tick=starvation_dmg,
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
    monster_behavior_stage = None
    monster_spawn_stage = None  # Phase B-2b: 条件付き placement の動的 spawn
    if scenario.monster_placements:
        from ai_rpg_world.application.world_graph.spot_attack_orchestrator import (
            AttackStatusEffectChance,
            SpotAttackOrchestrator,
        )
        from ai_rpg_world.application.monster.services.spot_monster_behavior_tick_service import (
            SpotMonsterBehaviorTickService,
        )

        # G1 finding (#343 trace 分析): モンスター攻撃成功時に確率で状態異常を
        # 付与する provider。survival_island_v2 では:
        # - island_wolf / feral_dog (野犬系) → 噛みつきで BLEEDING 50%, 12 tick
        # - swamp_snake (大蛇) → 毒の噛みつきで POISON 60%, 10 tick
        # - giant_crab (大カニ) → 挟む傷で BLEEDING 35%, 8 tick
        # 他テンプレ (現状は scenario 側に無いが将来追加された場合) は空。
        # 第一段階は scenario 駆動ではなく runtime 側で hardcode (v0)。将来は
        # MonsterTemplate に組み込んで scenario JSON 駆動にする (v1)。
        _ATTACK_EFFECTS_BY_TEMPLATE_NAME: dict[str, list[AttackStatusEffectChance]] = {
            "island_wolf": [AttackStatusEffectChance("bleeding", 0.5, 12)],
            "feral_dog": [AttackStatusEffectChance("bleeding", 0.5, 12)],
            "swamp_snake": [AttackStatusEffectChance("poison", 0.6, 10)],
            "giant_crab": [AttackStatusEffectChance("bleeding", 0.35, 8)],
        }

        def _monster_attack_status_provider(monster):
            """attacker monster の template_id を文字列に逆引きして effect を返す。

            scenario.monster_templates から (string_id -> template_id int) の
            マッピングを引いて、template_id から string_id を逆引きする。
            未登録なら空リスト (= 状態異常付与なし)。
            """
            try:
                tid_int = int(monster.template_id.value)
            except Exception:
                return []
            # scenario.monster_templates は string_id を持っているのでそこから逆引き
            for st in scenario.monster_templates:
                if int(st.template.template_id.value) == tid_int:
                    return _ATTACK_EFFECTS_BY_TEMPLATE_NAME.get(st.string_id, [])
            return []

        monster_attack_orchestrator = SpotAttackOrchestrator(
            spot_graph_repository=spot_graph_repo,
            monster_repository=monster_repo,
            player_status_repository=player_status_repo,
            attack_status_effect_provider=_monster_attack_status_provider,
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

            # 採番は static 配置で使った範囲とぶつからないよう開始値を 10_000 から。
            # 動的 spawn が同一 runtime 内で多数のスロットを 1000 回以上繰り返し
            # spawn/despawn しても安全な余裕を取る。
            def _make_counter(start: int):
                state = {"n": start}
                def _next() -> int:
                    state["n"] += 1
                    return state["n"]
                return _next

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
                monster_id_factory=_make_counter(10_000),
                loadout_id_factory=_make_counter(20_000),
                world_object_id_factory=_make_counter(2_000_000),
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
    # 構わない。registry 自体を outcome_resolution_stage が必要とする。
    # 後段で PipelineEventPublisher + handler を bind し、broadcast callback も追加する。
    from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
    from ai_rpg_world.domain.player.event.status_events import PlayerDownedEvent
    from ai_rpg_world.domain.player.service.player_outcome_registry import (
        PlayerOutcomeRegistry,
    )

    outcome_registry = PlayerOutcomeRegistry.new_for_players(
        [PlayerId(spawn.player_id) for spawn in scenario.player_spawns]
    )

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
        grace_ticks=30,
    )

    # ── Phase E-3b: outcome_resolution_stage ──
    # scenario.outcome_resolution_config が宣言されている場合のみ stage を作る。
    # 宣言が無い (例: 既存 v1 / abandoned_hospital) シナリオでは個別 outcome を
    # 使わず、stage は走らないので無影響。
    outcome_resolution_stage = None
    outcome_resolution_config = scenario.outcome_resolution_config
    if outcome_resolution_config is not None:
        from ai_rpg_world.application.world_graph.player_outcome_resolution_stage_service import (
            PlayerOutcomeResolutionStageService,
        )
        outcome_resolution_stage = PlayerOutcomeResolutionStageService(
            outcome_registry=outcome_registry,
            rescue_at_ticks=outcome_resolution_config.rescue_at_ticks,
            stranded_at_tick=outcome_resolution_config.stranded_at_tick,
            summit_spot_id=outcome_resolution_config.summit_spot_id,
            signal_fire_flag=outcome_resolution_config.signal_fire_flag,
            graph_provider=lambda: spot_graph_repo.find_graph(),
            flags_provider=world_flag_state.as_frozen_set,
            player_ids=[PlayerId(spawn.player_id) for spawn in scenario.player_spawns],
        )

    simulation_service = SpotGraphSimulationApplicationService(
        time_provider=time_provider,
        unit_of_work=InMemoryUnitOfWork(),
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
        outcome_resolution_stage=outcome_resolution_stage,
        death_grace_stage=death_grace_stage,
        llm_turn_trigger=sim_llm_trigger,
        # PR-N: tick stage で graph に積まれた events を heartbeat tick でも
        # observation pipeline 経由で flush する。これが無いと monster_behavior
        # 系の MonsterAteGroundItemEvent / MonsterFeltTemperatureDiscomfort 等
        # が「次に interaction/speech が来るまで遅延」または「永遠に届かない」
        # silent failure になる。
        # runtime はまだ未代入なので lambda で lazy bind する (= 呼出時に
        # 名前解決される)。runtime = WorldRuntime(...) が直後で実行される
        # 順序になっており、tick 開始までには確実に bound される。
        graph_event_flusher=lambda: runtime._process_graph_events(),
    )

    runtime = WorldRuntime(
        scenario=scenario,
        _spot_graph_repo=spot_graph_repo,
        _spot_interior_repo=spot_interior_repo,
        _player_status_repo=player_status_repo,
        _player_inventory_repo=player_inventory_repo,
        _item_repo=item_repo,
        _item_spec_repo=item_spec_repo,
        _world_flag_state=world_flag_state,
        _exploration_progress=exploration_progress,
        _movement_service=movement_service,
        _interaction_service=interaction_service,
        _exploration_service=exploration_service,
        _item_transfer_service=item_transfer_service,
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
        _sliding_window=sliding_window,
        _action_result_store=action_result_store,
        _encounter_memory=encounter_memory,
        # PR #448 (PR 3/6): cfg.prompt_section_order を使う (= env を再読しない)
        _context_strategy=_build_context_format_strategy_from_config(config),
        _time_provider=time_provider,
        _simulation_service=simulation_service,
        _travel_stage=travel_stage,
        _scenario_event_stage=scenario_event_stage,
        _scenario_event_progress=scenario_event_progress,
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
            else _include_todo_tools_from_env()
        ),
        # Prediction (#526 v0): expected_result 露出 policy を config から設定。
        _expected_result_policy=config.expected_result_policy,
    )
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
        if new_outcome is PlayerOutcomeEnum.DEAD:
            message = f"{actor_name}は倒れて動かなくなった。"
        elif new_outcome is PlayerOutcomeEnum.RESCUED:
            message = f"{actor_name}は救助された。"
        elif new_outcome is PlayerOutcomeEnum.STRANDED:
            message = f"{actor_name}は島に取り残されたままだ。"
        else:
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
        for pid in runtime.get_player_ids():
            runtime._emit_observation_directly(pid, output)

    outcome_registry.register_callback(_broadcast_outcome_change)
    # Issue #621: ダウン → DEAD 即時確定をやめ、30 tick の猶予を設ける。
    # grace_timer / grace_stage は simulation_service 構築時 (上の方) で
    # 既に作られているので、ここでは handler だけ pipeline に subscribe する。
    # PlayerDownedEvent → grace_timer.register、PlayerRevivedEvent →
    # grace_timer.cancel、tick stage が grace_ticks 経過後に DEAD 確定。
    from ai_rpg_world.application.player.handlers.player_revived_outcome_handler import (
        PlayerRevivedOutcomeHandler,
    )
    from ai_rpg_world.domain.player.event.status_events import PlayerRevivedEvent
    pipeline_event_publisher.register_handler(
        PlayerDownedEvent,
        PlayerDownedOutcomeHandler(
            outcome_registry=outcome_registry,
            grace_timer=death_grace_timer,
            current_tick_provider=lambda: int(runtime.current_tick().value),
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
    pipeline_event_publisher.register_handler(
        PlayerRevivedEvent,
        PlayerRevivedPostHocObservationHandler(
            grace_timer=death_grace_timer,
            observation_appender=observation_appender,
            current_tick_provider=lambda: int(runtime.current_tick().value),
            caregiver_name_resolver=lambda pid, _d=_caregiver_name_by_pid: (
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
    # PR4 (Encounter Memory): actor 本人の spot 到着を encounter として記録する
    # ための side handler を登録する。
    #
    # ⚠ 現状の有効範囲:
    # - **初回 spawn** の EntityEnteredSpotEvent は spawn loop 直後の
    #   ``graph.clear_events()`` で破棄されるため、本 handler は spawn では
    #   発火しない (= spawn の encounter は spawn loop 内で直接 observe する
    #   経路で記録済み)
    # - **travel 完了**は ``travel_stage.on_arrival`` callback 経由で記録される
    #   (= 上の wiring)
    # - 上記 2 経路のため、本 handler は現時点で production パスで fire しない
    #   **inert state** だが、将来 ``advance_tick`` 後に
    #   ``_process_graph_events`` を呼ぶ refactor や、interact / NPC AI の
    #   置換経路が graph events を publish するようになった時に、漏れなく
    #   encounter を補捉する forward-compat 防御として残しておく。
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
    # runtime からも access できるように field に保持。
    runtime._player_outcome_registry = outcome_registry

    speech_service = PlayerSpeechApplicationService(
        player_status_repository=player_status_repo,
        event_publisher=pipeline_event_publisher,
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
    # PR4: TIME_OF_DAY_IS / WEATHER_IS condition の評価用 provider 注入。
    # 「夜は釣りできない」「嵐の日は沖の釣り場へ行けない」のような
    # 行動制限条件を interaction precondition から評価できるようにする。
    # day_night_stage / weather_holder が無いシナリオでは provider は None の
    # ままで、該当 condition は「不在として fail」になる (silent skip 回避)。
    if day_night_stage is not None:
        interaction_service.set_time_of_day_phase_provider(
            lambda: day_night_stage.current_time_of_day().phase_name
        )
    interaction_service.set_weather_type_provider(
        lambda: (
            weather_holder["state"].weather_type.value
            if weather_holder.get("state") is not None
            else None
        )
    )
    # drop / pickup の witness 配信用。publisher は同じ pipeline を共有し、
    # SpotGraphRecipientStrategy が PlayerDroppedItemEvent / PlayerPickedUpItemEvent
    # を「同スポット・行為者除外」で他プレイヤーに観測として届ける。
    item_transfer_service.set_event_publisher(pipeline_event_publisher)
    # Phase v2-hunger: needs_decay_stage が starvation damage で
    # PlayerDownedEvent を積みうるので publisher を後付け注入する。
    # starvation_damage_per_tick=0 のシナリオでは publisher が居ても
    # events は積まれないので no-op。
    needs_decay_stage.set_event_publisher(pipeline_event_publisher)
    # PR #2: 状態異常 tick stage も同様に HP 0 → PlayerDownedEvent を流す。
    status_effects_stage.set_event_publisher(pipeline_event_publisher)
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
    runtime._observation_appender = observation_appender

    # Issue #283 後続: episodic memory pipeline の on/off。
    # episodic ON のときだけ scenario load 時に matcher + chunk coordinator +
    # passive recall を組み立てる。OFF なら従来動作。
    # PR #330: シナリオ非依存の builder に統一。world_episodic_wiring 経由の
    # 旧 alias も後方互換で生きているが、application 層から直接 import する。
    # #558 MEDIUM-1 後続: 親 gate を env 直読み (is_episodic_enabled) から
    # config.episodic_enabled に寄せ、ResolvedLlmRuntimeConfig 単一窓口に揃えた。
    # config=None のときは from_env() が LLM_EPISODIC_ENABLED を読むので、env で
    # 立てる experiment 経路は不変。explicit config を渡すと env でなく config が
    # 効くため「同 env を 2 経路で別解釈する」silent failure を構造で防げる。
    from ai_rpg_world.application.llm.wiring.episodic_stack import (
        build_episodic_stack,
        is_episodic_subjective_enabled,
    )
    if config.episodic_enabled:
        # Phase 3 Step 3e-3: ChunkCoordinator / Scheduler / passive_recall は
        # episode_store 経路で being_id 必須化済。world_runtime の aux Being 配線
        # を早期に確立し、各 player_spawn 分の Being を provision しておく。
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
            log_unconscious_context_enabled_state,
            resolve_belief_attribution_enabled,
            resolve_belief_consolidation_enabled,
            resolve_belief_evidence_enabled,
            resolve_error_driven_reinterpretation_enabled,
            resolve_error_gated_encoding_enabled,
            resolve_hearsay_enabled,
            resolve_memo_distill_enabled,
            resolve_pending_prediction_enabled,
            resolve_recall_hit_boost_enabled,
            resolve_salience_structured_failure_enabled,
            resolve_unconscious_context_enabled,
        )

        _belief_evidence_enabled = resolve_belief_evidence_enabled()
        log_belief_evidence_enabled_state(_belief_evidence_enabled)
        # U9a (予測誤差統一設計 部品5・誤差駆動再解釈 / default OFF): 実効的には
        # reinterpretation_enabled (段1) と PREDICTION_CONTEXT_ID_ENABLED (U1) の
        # 両方が ON でないと stamp 対象の recall observation が無く安全に縮退する。
        _error_driven_reinterpretation_enabled = (
            resolve_error_driven_reinterpretation_enabled()
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
        _recall_hit_boost_enabled = resolve_recall_hit_boost_enabled()
        log_recall_hit_boost_enabled_state(_recall_hit_boost_enabled)
        _recall_hit_boost_strength = 1
        # U4 (予測誤差統一設計 部品3 / default OFF): attribution + CONFIRMATION。
        # 実効的には U1 (PREDICTION_CONTEXT_ID_ENABLED) が ON でないと belief_ids
        # が流れてこないが、ここでは独立に flag を解決するだけに留める
        # (U1 flag OFF のまま本 flag だけ ON でも in_context_belief_ids は常に
        # 空になり安全に縮退する)。
        _belief_attribution_enabled = resolve_belief_attribution_enabled()
        log_belief_attribution_enabled_state(_belief_attribution_enabled)
        # P4 (reflect): 固着パスに目的への前進評価を足すか。
        from ai_rpg_world.application.llm.wiring.feature_flags import (
            log_goal_reflect_enabled_state,
            resolve_goal_reflect_enabled,
        )

        _goal_reflect_enabled = resolve_goal_reflect_enabled()
        log_goal_reflect_enabled_state(_goal_reflect_enabled)
        # U3b: 固着パス。BELIEF_EVIDENCE_ENABLED (PREDICTION_ERROR 転記) とは
        # 独立した flag だが、両方とも同じ evidence buffer を読み書きするので
        # どちらか一方でも ON なら buffer store 自体は作る。
        _belief_consolidation_enabled = resolve_belief_consolidation_enabled()
        log_belief_consolidation_enabled_state(_belief_consolidation_enabled)
        # U6: salience 判定 + STRUCTURED_FAILURE 転記 (default OFF)。他 2 flag
        # 同様、同じ evidence buffer を共有するので ON なら buffer store を作る
        # 条件に加える。
        _salience_structured_failure_enabled = (
            resolve_salience_structured_failure_enabled()
        )
        log_salience_structured_failure_enabled_state(
            _salience_structured_failure_enabled
        )
        # U8 (予測誤差統一設計 部品2・誤差ゲート付き符号化 / default OFF):
        # 境界 (2a, chunk_coordinator へ伝播) + 解像度 (2b, 下の subjective
        # service 構築時に salience_enabled と合わせて評価) を一括ゲートする。
        # evidence buffer とは無関係な独立 flag なので buffer store 条件には
        # 加えない。
        _error_gated_encoding_enabled = resolve_error_gated_encoding_enabled()
        log_error_gated_encoding_enabled_state(_error_gated_encoding_enabled)
        # U5: MEMO_DISTILL 転記 (default OFF)。他 3 flag 同様、同じ evidence
        # buffer を共有するので ON なら buffer store を作る条件に加える。
        _memo_distill_enabled = resolve_memo_distill_enabled()
        log_memo_distill_enabled_state(_memo_distill_enabled)
        # U7 (予測誤差統一設計 / 無意識コンテキスト / default OFF): belief top-K +
        # L5 を chunk 主観補完 LLM に渡すか。他 flag と独立 (evidence buffer は
        # 使わない = 読み取り専用の追加コンテキストなので buffer store 条件には
        # 加えない)。
        _unconscious_context_enabled = resolve_unconscious_context_enabled()
        log_unconscious_context_enabled_state(_unconscious_context_enabled)
        # U10a (予測誤差統一設計 部品6・pending prediction / default OFF):
        # 抽出・保持・再浮上を一括ゲートする。evidence buffer とは無関係な
        # 独立 flag (別の per-Being store を使う) なので buffer store 条件には
        # 加えない。
        _pending_prediction_enabled = resolve_pending_prediction_enabled()
        log_pending_prediction_enabled_state(_pending_prediction_enabled)
        _hearsay_enabled = resolve_hearsay_enabled()
        log_hearsay_enabled_state(_hearsay_enabled)
        # P5 (目的層 G1): GOAL_STORE_ENABLED ON のとき goal store を構築し
        # runtime に保持する。【現在の目的】provider (prompt builder 側) と実験
        # snapshot stub がここから拾う。OFF なら None のまま (静的シナリオ文字列)。
        from ai_rpg_world.application.llm.wiring.feature_flags import (
            log_goal_store_enabled_state,
            resolve_goal_store_enabled,
        )

        _goal_store_enabled = resolve_goal_store_enabled()
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
            resolve_goal_revision_enabled,
        )

        _goal_revision_requested = resolve_goal_revision_enabled()
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
        if is_episodic_subjective_enabled():
            from ai_rpg_world.application.llm.services.episodic_chunk_subjective_fields import (
                EpisodicChunkSubjectiveFieldsService,
            )
            from ai_rpg_world.application.llm.services.episodic_subjective_completion_schedulers import (
                ThreadPoolEpisodicSubjectiveScheduler,
            )
            from ai_rpg_world.application.llm.wiring._llm_client_factory import (
                create_llm_client_from_env,
            )
            from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient

            try:
                _client = create_llm_client_from_env()
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
                # world_view) は RollingSummary 使用時のみ sliding_window が
                # get_long_summary_text を実装するので、無ければ渡さない
                # (= 従来通り省略される)。
                _unconscious_context_provider = None
                if _unconscious_context_enabled:
                    from ai_rpg_world.application.llm.wiring.unconscious_context_provider import (
                        build_unconscious_context_provider,
                    )

                    _get_long_summary_text = getattr(
                        sliding_window, "get_long_summary_text", None
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
                # 触るため、Resolver+WorldId を伝播する (= aux_being_* は本 runtime
                # の __init__ で構築済)
                subjective_scheduler = ThreadPoolEpisodicSubjectiveScheduler(
                    _subjective_service,
                    shared_episode_store,
                    max_workers=1,
                    max_queue_size=100,
                    trace_recorder_provider=lambda: runtime._trace_recorder,
                    current_tick_provider=runtime.current_tick,
                    being_attachment_resolver=runtime._aux_being_resolver,
                    default_world_id=runtime._aux_being_default_world_id,
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
        _semantic_enabled = (
            _semantic_top_k > 0
            or _semantic_gist_enabled
            or _belief_consolidation_enabled
            or _unconscious_context_enabled
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
                    create_llm_client_from_env,
                )

                try:
                    _gist_client = create_llm_client_from_env()
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
                create_llm_client_from_env,
            )

            try:
                _reinterp_client = create_llm_client_from_env()
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
                create_llm_client_from_env,
            )
            from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient

            try:
                _belief_consolidation_client = create_llm_client_from_env()
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
            sliding_window_memory=sliding_window,
            action_result_store=action_result_store,
            # trace_recorder は set_trace_recorder で後から差し込まれるので
            # provider 経由で参照。chunk 書き込みごとに
            # TraceEventKind.EPISODIC_CHUNK_WRITTEN が記録される。
            trace_recorder_provider=lambda: runtime._trace_recorder,
            current_tick_provider=runtime.current_tick,
            subjective_completion_scheduler=subjective_scheduler,
            persona_block_provider=persona_provider,
            episode_store=shared_episode_store,
            # Phase 3 Step 3e-3: episode_store 経路を being_id 統一済のため、
            # aux Being 配線をそのまま使う
            being_attachment_resolver=runtime._aux_being_resolver,
            default_world_id=runtime._aux_being_default_world_id,
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
                being_attachment_resolver=runtime._aux_being_resolver,
                default_world_id=runtime._aux_being_default_world_id,
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
    return runtime


# PR #451 (PR 6/6): _wire_short_term_llm_services は廃止。
# 旧来は ctor で空殻 (summary_service=None) を作り、後で setter 注入する 2 段階
# 構築だったが、setter 呼び忘れで silent failure を量産 (PR #444 の実害)。
# 本 PR で _build_short_term_memory に統合し ctor 一発注入に変更したため、
# 後注入用のこの helper は不要になった。
