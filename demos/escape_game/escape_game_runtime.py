"""廃病院脱出ゲームのランタイム。

シナリオ JSON → インメモリリポジトリ → アプリケーションサービス をワイヤリングし、
プログラム的にアクションを実行できるようにする。

LLM エージェントが**実際に**受け取る観測テキスト・ツール定義・ラベル解決コンテキストを
そのまま可視化する。デモ専用の加工は行わない。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, ClassVar, Dict, FrozenSet, List, Optional, Tuple

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
from ai_rpg_world.application.llm.services.tool_catalog.memory import get_memory_specs
from ai_rpg_world.application.llm.services.sliding_window_memory import DefaultSlidingWindowMemory
from ai_rpg_world.application.llm.services.action_result_store import DefaultActionResultStore
from ai_rpg_world.application.llm.services.context_format_strategy import (
    SectionBasedContextFormatStrategy,
)
from ai_rpg_world.application.llm.services.recent_events_formatter import DefaultRecentEventsFormatter
from ai_rpg_world.application.llm.services.in_memory_todo_store import InMemoryTodoStore
from ai_rpg_world.application.llm.services.executors.todo_executor import TodoToolExecutor
from ai_rpg_world.application.llm.services.escape_llm_prompt import (
    EscapeCharacterPromptInput,
    build_escape_system_prompt,
    build_persona_block_from_escape_character,
    safe_world_intro_text,
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
from demos.escape_game.pipeline_event_publisher import PipelineEventPublisher
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


class EscapeGameStandaloneNoopLlmTurnTrigger(ILlmTurnTrigger):
    """単体 `create_escape_game_runtime` 用の ILlmTurnTrigger 実装。

    当ファクトリは LLM オーケストラを内蔵しない。ティック後フック
    :class:`SpotGraphSimulationApplicationService` 契約を満たすためのプレースホルダ。
    プレゼンテーション層のセッション生成後は
    :meth:`EscapeGameRuntime.set_simulation_llm_turn_trigger` で本物の
    トリガ（例: セッションの ``_EscapeGameLlmTurnTrigger``）に差し替える。
    """

    def schedule_turn(self, player_id: PlayerId) -> None:  # noqa: ARG002
        return None

    def run_scheduled_turns(self) -> None:
        return None


def _other_explorer_names_for_escape_system_prompt(
    spawns: Tuple[PlayerSpawnConfig, ...],
    escape_character: Optional[EscapeCharacterPromptInput],
) -> tuple[str, ...]:
    """【同じ局面にいる者】用の表示名。自身（LLM ペルソナ）に対応するスポーンは含めない。

    シナリオ上の他プレイヤー全員名ではなく、同席する他者のみ述べるため、単体プレイでは空になる。
    `escape_character` 未指定時は `player_spawns[0]` を操作対象（ペルソナのフォールバック名と同じ扱い）とみなし除外する。
    """
    if not spawns:
        return ()
    self_spawn: Optional[PlayerSpawnConfig] = None
    if escape_character is not None:
        cid = (escape_character.character_id or "").strip()
        if cid:
            for s in spawns:
                if s.string_id == cid:
                    self_spawn = s
                    break
        if self_spawn is None:
            cname = (escape_character.name or "").strip()
            if cname:
                for s in spawns:
                    if s.name == cname:
                        self_spawn = s
                        break
    if self_spawn is None:
        self_spawn = spawns[0]
    return tuple(s.name for s in spawns if s is not self_spawn)


@dataclass
class EscapeGameRuntime:
    """脱出ゲームデモの実行ランタイム（全てインメモリ）。"""

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
    _time_provider: InMemoryGameTimeProvider
    _simulation_service: SpotGraphSimulationApplicationService
    _scenario_event_stage: SpotGraphScenarioEventStageService
    _scenario_event_progress: InMemorySpotGraphScenarioEventProgressStore
    _environment_stage: SpotGraphEnvironmentStageService
    _current_weather: Any
    # 昼夜サイクル stage (Phase B-1)。シナリオに day_night_config が無ければ None。
    _day_night_stage: Optional[SpotGraphDayNightStageService] = field(default=None, repr=False)
    _tick: int = 0
    # LLM 脱出用（セッション単位で構築）
    # _escape_llm_system_prompt: 全プレイヤー共通の system prompt (legacy / 単体プレイ用)
    # _escape_llm_system_prompts_by_player_id: Issue #264 第16回実験で発見された
    # 「player 2 (リン) が「リン、〜」と自分名で speech する自呼び回帰」を解消するため、
    # シナリオに複数 player_spawns がある場合は player ごとに persona を埋めた system
    # prompt を持つ。dict が空 / 該当 id 無しなら _escape_llm_system_prompt にフォールバック。
    _escape_llm_system_prompt: str = field(default="", repr=False)
    _escape_llm_system_prompts_by_player_id: Dict[int, str] = field(
        default_factory=dict, repr=False
    )
    _todo_store: InMemoryTodoStore = field(default_factory=InMemoryTodoStore, repr=False)
    _todo_tool_executor: Optional[TodoToolExecutor] = field(default=None, repr=False)
    # シナリオ実行 trace の recorder。未設定なら NullTraceRecorder にフォールバック
    # (Phase 1d 配線)。
    _trace_recorder: Any = field(default=None, repr=False)
    # B-4: LLM に提示するツールセットの mode。``True`` (既定) なら TODO 系も
    # 含む従来構成、``False`` なら純スポットグラフ + speech のみ。
    # Issue #155 (TODO 設計の再評価) の判断材料を取るための比較実験用。
    _include_todo_tools: bool = field(default=True, repr=False)
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

    def advance_tick(self) -> int:
        tick = self._simulation_service.tick()
        self._tick = tick.value
        return tick.value

    def set_trace_recorder(self, recorder: Any) -> None:
        """シナリオ実行 trace の recorder を後から差し込む (Phase 1d 配線)。

        ``create_session`` などで escape_game_runtime を構築した後に
        外側から trace を有効化する用途。memo executor は lazy 構築なので
        既に作成済みでもこのフィールドが反映される。
        """
        self._trace_recorder = recorder
        # 既に memo executor が wire 済みなら作り直してから recorder を行き渡らせる
        if self._todo_tool_executor is not None:
            self._todo_tool_executor = None
            self._wire_auxiliary_tool_stack()

    @property
    def trace_recorder(self) -> Any:
        return self._trace_recorder

    def set_simulation_llm_turn_trigger(
        self, trigger: Optional[ILlmTurnTrigger]
    ) -> None:
        """ティック後の :meth:`ILlmTurnTrigger.run_scheduled_turns` に使う実装を差し替える。

        プレゼン層の ``_EscapeGameLlmWiring`` など、実際に LLM を起動するトリガに
        切り替える。単体デモの既定は :class:`EscapeGameStandaloneNoopLlmTurnTrigger`。
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
        _escape_llm_system_prompts_by_player_id に該当 id があればそれを返す
        (rich persona)、なければ legacy の _escape_llm_system_prompt にフォールバック
        (単体プレイの旧挙動互換)。
        """
        per_player = self._escape_llm_system_prompts_by_player_id.get(
            int(player_id.value) if hasattr(player_id, "value") else int(player_id)
        )
        if per_player is not None:
            return per_player
        return self._escape_llm_system_prompt

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
        """
        spot = [defn for defn, _ in get_spot_graph_specs()]
        if not self._include_todo_tools:
            return spot
        todo = [defn for defn, _ in get_memory_specs(todo_enabled=True)]
        return spot + todo

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
        events = list(graph.get_events())
        graph.clear_events()
        if not events:
            return
        if self._speech_event_publisher is None:
            # 構築途中 (set_event_publisher 注入前) には起こり得る。
            # silent skip + 後続を継続。
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
        # ActionFailedObservationEmitter が aware を発行するため、escape_game
        # 経路の naive と混ざると EpisodicChunkCoordinator の obs_slice
        # フィルタで TypeError になる。詳細: docs/episodic_memory フォローアップ。
        appender.append(
            player_id, output, datetime.now(timezone.utc), self._time_label()
        )
        scheduler = self._observation_turn_scheduler
        if scheduler is not None:
            scheduler.maybe_schedule(player_id, output)

    def _record_action_result(
        self, player_id: PlayerId, action_summary: str, result_summary: str,
    ) -> None:
        # tz-aware UTC で統一 (詳細は _emit_observation_directly のコメント参照)
        self._action_result_store.append(
            player_id,
            action_summary=action_summary,
            result_summary=result_summary,
            occurred_at=datetime.now(timezone.utc),
        )
        # Issue #283 後続: episodic memory が有効なら、action_result が
        # store に積まれた直後に chunk_coordinator を起動する。chunk
        # coordinator が observation buffer を drain → sliding window に流し、
        # 必要なら episode を 1 件以上 store に書く。失敗は memory pipeline
        # の責務に留め、本来の action 完了は止めない。
        if self._episodic_stack is not None:
            try:
                self._episodic_stack.chunk_coordinator.after_action_recorded(player_id)
            except Exception:
                logger.exception(
                    "episodic chunk_coordinator.after_action_recorded failed "
                    "for player=%s",
                    player_id.value,
                )

    def _drain_buffer_to_sliding_window(self, player_id: PlayerId) -> List[ObservationEntry]:
        """観測バッファをスライディングウィンドウに移す。溢れた観測を返す。"""
        drained = self._obs_buffer.drain(player_id)
        if not drained:
            return []
        return self._sliding_window.append_all(player_id, drained)

    def _wire_auxiliary_tool_stack(self) -> None:
        """TODO ツール実行器を遅延初期化する。"""
        if self._todo_tool_executor is not None:
            return
        self._todo_tool_executor = TodoToolExecutor(
            self._todo_store,
            sliding_window=self._sliding_window,
            action_result_store=self._action_result_store,
            current_tick_provider=self.current_tick,
            trace_recorder=self._trace_recorder,
        )

    def run_llm_auxiliary_tool(
        self, player_id: PlayerId, name: str, arguments: Dict[str, Any]
    ) -> LlmCommandResultDto:
        """TODO 系ツールを実行する。"""
        self._wire_auxiliary_tool_stack()
        assert self._todo_tool_executor is not None
        handlers = self._todo_tool_executor.get_handlers()
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

    _ESCAPE_GAME_OBJECTIVE_TEXT = (
        "- この廃墟から外へ脱出する。\n"
        "- 必要なら手がかり（物証・記録）を集め、判断材料にする。"
    )
    _ESCAPE_GAME_ACTION_INSTRUCTION = (
        "利用可能なツールから、次に取るべき 1 つの行動だけを選んでください。"
    )

    # Issue #227 後続 HIGH-3 改善: stateless formatter / strategy を class-level
    # に持ち、build_full_prompt の毎回 new を避ける + 本家 DefaultPromptBuilder と
    # 同じインスタンスタイプを使うことを明示する。
    _recent_events_formatter: ClassVar[DefaultRecentEventsFormatter] = (
        DefaultRecentEventsFormatter()
    )
    _context_strategy: ClassVar[SectionBasedContextFormatStrategy] = (
        SectionBasedContextFormatStrategy()
    )

    def _get_or_build_default_prompt_builder(self) -> "DefaultPromptBuilder":
        """本家 DefaultPromptBuilder のインスタンスを lazy 構築してキャッシュする。

        Issue #227 後続 HIGH-3 Part 2: escape_game の prompt 組み立てを
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
        from demos.escape_game.default_prompt_builder_adapters import (
            EscapeGameAvailableToolsProvider,
            EscapeGameProfileRepositoryAdapter,
            EscapeGameSystemPromptBuilder,
            EscapeGameWorldQueryAdapter,
        )

        core = PromptBuilderCoreServices(
            observation_buffer=self._obs_buffer,
            sliding_window_memory=self._sliding_window,
            action_result_store=self._action_result_store,
            world_query_service=EscapeGameWorldQueryAdapter(self),
            player_profile_repository=EscapeGameProfileRepositoryAdapter(self),
            current_state_formatter=self._formatter,
            recent_events_formatter=self._recent_events_formatter,
            context_format_strategy=self._context_strategy,
            system_prompt_builder=EscapeGameSystemPromptBuilder(self),
            available_tools_provider=EscapeGameAvailableToolsProvider(),
        )
        sections = PromptSectionProviders(
            objective_text_provider=lambda _pid: self._ESCAPE_GAME_OBJECTIVE_TEXT,
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
            episodic_config = EpisodicRecallConfig(
                passive_recall=self._episodic_stack.passive_recall,
                noun_matcher=self._episodic_stack.noun_matcher,
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
        )
        self._cached_default_prompt_builder = builder
        return builder

    def build_full_prompt(self, player_id: PlayerId) -> dict:
        """各プレイヤーが LLM ターンで実際に受け取る完全なプロンプトを構築する。

        Issue #227 後続 HIGH-3 Part 2: 本家 DefaultPromptBuilder.build() に統合した。
        section 組み立て・recent_events・active_memos・tile-map field 制御は
        DefaultPromptBuilder 内部で処理される。escape_game 固有の部分は adapter
        (default_prompt_builder_adapters.py) 経由で注入する:
        - WorldQuery 相当: build_llm_context + _build_minimal_player_state_dto
        - system_prompt: precomputed _escape_llm_system_prompt
        - objective/inventory section: provider 経由

        return shape:
            {
                "messages": [
                    {"role": "system", "content": ...},
                    {"role": "user", "content": ...},
                ],
                "tools": [<tool name str>, ...],     # escape_game は名前 list
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

        # tool_runtime_context は escape_game 独自の build_llm_context 経由で取得
        ctx = self.build_llm_context(player_id)

        return {
            "messages": result["messages"],
            "tools": [d.name for d in self.get_tool_definitions()],
            "tool_runtime_context": ctx.tool_runtime_context,
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
        self._record_action_result(
            player_id,
            f"「{obj_label}」に対して{action_ja}を行った",
            result_text,
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
        self._record_action_result(
            player_id,
            f"スロット{slot_id_value}のアイテムを地面に置いた",
            result_text,
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

    def do_explore(self, player_id: PlayerId) -> SpotExplorationResultDto:
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
        )
        return result

    def do_move(self, player_id: PlayerId, dest_spot_str_id: str) -> None:
        from_name = self.get_player_spot_name(player_id)
        dest_int = self.id_mapper.get_int("spot", dest_spot_str_id)
        dest_sid = SpotId.create(dest_int)
        inv = self._player_inventory_repo.find_by_id(player_id)
        owned: FrozenSet[ItemSpecId] = frozenset()
        if inv:
            owned = collect_owned_item_spec_ids_from_inventory(inv, self._item_repo)
        flags = self._world_flag_state.as_frozen_set()
        self._movement_service.start_travel_to_spot(player_id, dest_sid, owned, flags)
        for _ in range(200):
            self.advance_tick()
            status = self._player_status_repo.find_by_id(player_id)
            if status is None or status.spot_navigation_state is None:
                break
            if not status.spot_navigation_state.is_traveling:
                break
        self._process_graph_events()
        dest_name = self._spot_graph_repo.find_graph().get_spot(dest_sid).name
        self._record_action_result(
            player_id,
            f"「{from_name}」から「{dest_name}」へ移動した",
            f"「{dest_name}」に到着した",
        )

    def do_wait(self, player_id: PlayerId, reason: str = "") -> int:
        tick = self.advance_tick()
        r = (reason or "").strip()
        if r:
            self._record_action_result(
                player_id,
                f"待機した（理由: {r}）",
                f"時間が進んだ（tick={tick}）",
            )
        else:
            self._record_action_result(
                player_id,
                "短く待機した",
                f"時間が進んだ（tick={tick}）",
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
        tick = self.current_tick()
        hours = (tick * 5) % (24 * 60)
        h, m = divmod(hours, 60)
        return f"深夜 {h}:{m:02d}" if h < 6 else f"{h}:{m:02d}"

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


def _escape_llm_ssot_enabled_from_env() -> bool:
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


def create_escape_game_runtime(
    scenario_path: Path,
    *,
    escape_character: Optional[EscapeCharacterPromptInput] = None,
    llm_turn_trigger: Optional[ILlmTurnTrigger] = None,
    include_todo_tools: Optional[bool] = None,
) -> EscapeGameRuntime:
    """シナリオ JSON からゲームランタイムを構築する。

    Args:
        llm_turn_trigger: 省略時は :class:`EscapeGameStandaloneNoopLlmTurnTrigger`。
            スポットグラフのティック後フック用。プレゼン層のセッションでは
            ``runtime.set_simulation_llm_turn_trigger(…)`` で本物に差し替え可能。
        include_todo_tools: ``True`` で TODO 系を含める従来構成、``False`` で
            純スポットグラフモード (TODO 系を除外、speech は残す)。``None``
            (既定) の場合は環境変数 ``LLM_TOOL_MODE`` から解決する。Issue #155
            (TODO 設計の再評価) の判断材料を取るための比較実験用。
    """
    loader = ScenarioLoader()
    scenario = loader.load_from_file(scenario_path)

    fallback_name = (
        scenario.player_spawns[0].name if scenario.player_spawns else "探索者"
    )
    persona_block = build_persona_block_from_escape_character(
        escape_character,
        fallback_display_name=fallback_name,
    )
    safe_intro = safe_world_intro_text(scenario.metadata)
    participants = _other_explorer_names_for_escape_system_prompt(
        scenario.player_spawns, escape_character
    )
    system_prompt_text = build_escape_system_prompt(
        world_title=scenario.metadata.title,
        persona_block=persona_block,
        safe_intro=safe_intro,
        participant_names=participants,
        enable_string_seed_of_thought=_escape_llm_ssot_enabled_from_env(),
    )

    # Issue #264 第16回実験 fix: シナリオに複数 player_spawns がある場合、
    # 各 player に persona を埋めた system prompt を個別に構築する。
    # これにより player 2 (例: リン) は「自分はリン」という persona block を
    # 受け取り、自呼び回帰 (リンが「リン、」と speech する) が解消される。
    #
    # ロジック:
    #   - escape_character が指定されていればその player_id は escape_character の
    #     rich persona を使う (旧挙動と一致)
    #   - その他の player_id は fallback persona (= スポーン名から生成された
    #     最小ペルソナ) を使う
    #   - participant_names は各 player から見た「自分以外の探索者」のリスト
    system_prompts_by_player_id: Dict[int, str] = {}
    if len(scenario.player_spawns) > 1:
        # escape_character に一致する spawn を特定
        escape_spawn: Optional[PlayerSpawnConfig] = None
        if escape_character is not None:
            ec_cid = (escape_character.character_id or "").strip()
            ec_name = (escape_character.name or "").strip()
            for s in scenario.player_spawns:
                if (ec_cid and s.string_id == ec_cid) or (ec_name and s.name == ec_name):
                    escape_spawn = s
                    break

        for spawn in scenario.player_spawns:
            # この spawn から見た「他者」名リスト
            other_names = tuple(s.name for s in scenario.player_spawns if s is not spawn)
            # この spawn のペルソナ:
            #   - escape_character がこの spawn を指している → rich persona
            #   - そうでなければ fallback (スポーン名ベース)
            if escape_character is not None and spawn is escape_spawn:
                this_persona = persona_block  # rich (既に上で構築済み)
            else:
                this_persona = build_persona_block_from_escape_character(
                    None,  # fallback path
                    fallback_display_name=spawn.name,
                )
            system_prompts_by_player_id[int(spawn.player_id)] = (
                build_escape_system_prompt(
                    world_title=scenario.metadata.title,
                    persona_block=this_persona,
                    safe_intro=safe_intro,
                    participant_names=other_names,
                    enable_string_seed_of_thought=_escape_llm_ssot_enabled_from_env(),
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
        spec = ItemSpecReadModel(
            item_spec_id=item_def.spec_id,
            name=item_def.name,
            item_type=ItemType.QUEST,
            rarity=Rarity.COMMON,
            description=item_def.description,
            max_stack_size=MaxStackSize(1),
            is_light_source=item_def.is_light_source,
        )
        item_spec_repo.save(spec)

    player_status_repo = InMemoryPlayerStatusRepository(data_store)
    player_inventory_repo = InMemoryPlayerInventoryRepository(data_store)

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
        for placement in scenario.monster_placements:
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
    interaction_service = SpotInteractionApplicationService(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        player_inventory_repository=player_inventory_repo,
        item_repository=item_repo,
        item_spec_repository=item_spec_repo,
        world_flag_state=world_flag_state,
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
    # physical_map 依存で escape_game では発火しないため、本サービスが
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

    def _build_inventory(pid: PlayerId) -> tuple:
        inv = player_inventory_repo.find_by_id(pid)
        if inv is None:
            return ()
        # spec_id 別に集約しつつ「代表 instance」のスロット番号と instance id を覚える。
        # 代表 = 最初に発見したスロットの instance。drop_item ツールが
        # 「I1 = 流木 (x2)」のうち1個を落とすときの target になる。
        seen_specs: dict[int, list] = {}
        for slot_id in range(inv._max_slots):
            from ai_rpg_world.domain.player.value_object.slot_id import SlotId
            iid = inv.get_item_instance_id_by_slot(SlotId(slot_id))
            if iid is None:
                continue
            item = item_repo.find_by_id(iid)
            if item is None:
                continue
            sid = item.item_spec.item_spec_id.value
            if sid not in seen_specs:
                name = item.item_spec.name
                seen_specs[sid] = [name, 0, slot_id, iid.value]
            seen_specs[sid][1] += 1
        return tuple(
            SpotGraphInventoryItemEntry(
                item_spec_id=sid,
                name=info[0],
                quantity=info[1],
                slot_id=info[2],
                item_instance_id=info[3],
            )
            for sid, info in seen_specs.items()
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
    # 「昼夜の概念なし」状態にする (既存 escape_game / 廃病院は影響なし)。
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
    )

    # ── 観測パイプライン構築 ──
    # Issue #227 PR-5 (tile-map 除去): physical_map_repository=None で resolver を
    # 組み立てる。tile-map 依存の strategy (Pursuit / Monster / Combat / Harvest /
    # Default の世界座標フォールバック) は escape_game では関連 event が発火しないため
    # inert で、resolver 内部の NullWorldObjectToPlayerResolver で安全に処理される。
    # PlayerSpokeEvent は SpotGraphSpeechRecipientStrategy (hop-based) で処理される。
    #
    # WARN: 将来 tile-map ベースの event (Pursuit/Monster/Combat/Harvest 等) を
    # escape_game に持ち込む場合は、physical_map_repository を実装した上で渡す必要がある。
    obs_resolver = create_observation_recipient_resolver(
        player_status_repository=player_status_repo,
        physical_map_repository=None,
        spot_graph_repository=spot_graph_repo,
    )

    obs_formatter = ObservationFormatter(spot_graph_repository=spot_graph_repo)
    obs_formatter._name_resolver.player_name = lambda pid: player_name_map.get(  # type: ignore[assignment]
        pid.value, f"プレイヤー({pid.value})"
    )

    obs_pipeline = ObservationPipeline(
        resolver=obs_resolver,
        formatter=obs_formatter,
        player_status_repository=player_status_repo,
    )
    obs_buffer = DefaultObservationContextBuffer()
    sliding_window = DefaultSlidingWindowMemory()
    action_result_store = DefaultActionResultStore()

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
    scenario_event_progress = InMemorySpotGraphScenarioEventProgressStore()
    # 評価器は scenario_event_stage と reactive_binding_stage で共有する。
    # weather_state_provider を渡すことで WEATHER_IS 条件が解ける。
    condition_evaluator = ScenarioConditionEvaluator(
        world_flag_state=world_flag_state,
        spot_interior_repository=spot_interior_repo,
        player_status_repository=player_status_repo,
        player_inventory_repository=player_inventory_repo,
        item_repository=item_repo,
        weather_state_provider=lambda: weather_holder["state"],
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
    sim_llm_trigger: ILlmTurnTrigger = (
        llm_turn_trigger
        if llm_turn_trigger is not None
        else EscapeGameStandaloneNoopLlmTurnTrigger()
    )
    # tick 経過で空腹 / 疲労が緩やかに増加するステージ。survival_island のような
    # 長期サバイバルでは生存圧の本体になる。escape_game v1 (廃病院) でも
    # 120 tick の間に空腹 100% に到達するが現状の lose 条件は tick_limit のみ
    # なので挙動に大きな影響はない。
    needs_decay_stage = SpotGraphNeedsDecayStageService(
        player_status_repository=player_status_repo,
    )

    # Phase B-2a: モンスター攻撃のオーケストレーターと behavior tick service。
    # placements が空ならどちらも構築しないことで、既存シナリオ
    # (廃病院 等) の挙動を一切変えない。
    monster_attack_orchestrator = None
    monster_behavior_stage = None
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
        monster_behavior_stage=monster_behavior_stage,
        llm_turn_trigger=sim_llm_trigger,
    )

    runtime = EscapeGameRuntime(
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
        _ui_context_builder=SpotGraphUiContextBuilder(),
        _obs_pipeline=obs_pipeline,
        _obs_buffer=obs_buffer,
        _sliding_window=sliding_window,
        _action_result_store=action_result_store,
        _time_provider=time_provider,
        _simulation_service=simulation_service,
        _scenario_event_stage=scenario_event_stage,
        _scenario_event_progress=scenario_event_progress,
        _environment_stage=environment_stage,
        _current_weather=weather_holder,
        _day_night_stage=day_night_stage,
        _escape_llm_system_prompt=system_prompt_text,
        _escape_llm_system_prompts_by_player_id=system_prompts_by_player_id,
        _include_todo_tools=(
            include_todo_tools
            if include_todo_tools is not None
            else _include_todo_tools_from_env()
        ),
    )
    scenario_event_stage.set_message_callback(
        runtime._append_scenario_event_observation
    )
    if weather_config is None or weather_config.announce_changes:
        environment_stage.set_weather_changed_callback(runtime._append_weather_observation)

    # ── PR 2/6 (#227): 任意の DomainEvent を ObservationPipeline 経由で配信する ──
    # PR 2 では PlayerSpokeEvent 用に InMemoryEventPublisher を使い handler を
    # 個別登録していたが、PR 6 で interaction_service など他経路の event も
    # pipeline に流す必要が出たため、event 型ごとの登録ではなく「全 event
    # を pipeline へ流す」publisher に置き換える。chore (#240 後続) で
    # module-level に切り出し。
    # Issue #276: 観測 trace 可視化のため、buffer に積むタイミングで
    # ``TraceEventKind.OBSERVATION`` を記録する。trace_recorder は
    # ``set_trace_recorder`` で後から差し込まれるので provider 経由で参照。
    observation_appender = ObservationAppender(
        buffer=obs_buffer,
        trace_recorder_provider=lambda: runtime._trace_recorder,
        current_tick_provider=runtime.current_tick,
    )
    pipeline_event_publisher = PipelineEventPublisher(runtime)
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
    # drop / pickup の witness 配信用。publisher は同じ pipeline を共有し、
    # SpotGraphRecipientStrategy が PlayerDroppedItemEvent / PlayerPickedUpItemEvent
    # を「同スポット・行為者除外」で他プレイヤーに観測として届ける。
    item_transfer_service.set_event_publisher(pipeline_event_publisher)
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
    # 環境変数 LLM_EPISODIC_ENABLED=1 のときだけ scenario load 時に matcher
    # + chunk coordinator + passive recall を組み立てる。未設定なら従来動作。
    from demos.escape_game.escape_episodic_wiring import (
        build_escape_episodic_stack,
        is_episodic_enabled,
    )
    if is_episodic_enabled():
        runtime._episodic_stack = build_escape_episodic_stack(
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
        )

    return runtime
