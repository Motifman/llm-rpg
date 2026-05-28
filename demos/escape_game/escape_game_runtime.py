"""廃病院脱出ゲームのランタイム。

シナリオ JSON → インメモリリポジトリ → アプリケーションサービス をワイヤリングし、
プログラム的にアクションを実行できるようにする。

LLM エージェントが**実際に**受け取る観測テキスト・ツール定義・ラベル解決コンテキストを
そのまま可視化する。デモ専用の加工は行わない。
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

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
from ai_rpg_world.domain.common.domain_event import DomainEvent
from ai_rpg_world.domain.common.event_publisher import EventPublisher
from ai_rpg_world.domain.player.enum.player_enum import SpeechChannel
from ai_rpg_world.domain.player.event.conversation_events import PlayerSpokeEvent
from ai_rpg_world.infrastructure.repository.in_memory_physical_map_repository import (
    InMemoryPhysicalMapRepository,
)

from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import InMemoryItemRepository
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
    _tick: int = 0
    # LLM 脱出用（セッション単位で構築）
    _escape_llm_system_prompt: str = field(default="", repr=False)
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
    _speech_event_publisher: Optional[EventPublisher] = field(
        default=None, repr=False
    )
    _observation_appender: Optional[ObservationAppender] = field(default=None, repr=False)
    # turn_scheduler はセッション作成時に create_session で注入される
    # (LlmTurnTrigger と llm_player_resolver は wiring で組み立てる必要があるため)
    _observation_turn_scheduler: Optional[ObservationTurnScheduler] = field(
        default=None, repr=False
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

    def do_say(self, speaker_player_id: PlayerId, content: str) -> None:
        """speech_say ツールの実行口。PlayerSpokeEvent を fire し、ObservationPipeline 経由で
        配信する。距離 gating (SoundPropagationService) は recipient strategy 側で行われる。

        旧 ``_append_agent_speech`` (全プレイヤー broadcast) を本メソッドが置き換える
        (Issue #227 PR 2)。
        """
        if self._speech_service is None:
            return
        self._speech_service.speak(
            SpeakCommand(
                speaker_player_id=int(speaker_player_id.value),
                content=content,
                channel=SpeechChannel.SAY,
                target_player_id=None,
            )
        )

    def do_whisper(
        self,
        speaker_player_id: PlayerId,
        content: str,
        target_player_id: PlayerId,
    ) -> None:
        """whisper ツールの実行口。同一スポット内の宛先のみに届く。"""
        if self._speech_service is None:
            return
        self._speech_service.speak(
            SpeakCommand(
                speaker_player_id=int(speaker_player_id.value),
                content=content,
                channel=SpeechChannel.WHISPER,
                target_player_id=int(target_player_id.value),
            )
        )

    # ── 後方互換ヘルパー（テスト用） ──

    def build_observation(self, player_id: PlayerId) -> str:
        """E2E テスト用の簡易観測テキスト。build_llm_context のテキスト部分を返す。"""
        return self.build_llm_context(player_id).current_state_text

    def build_available_tools(self, player_id: PlayerId) -> str:
        """E2E テスト用のツール一覧テキスト。"""
        names = [d.name for d in self.get_tool_definitions()]
        return ", ".join(names)

    def build_system_prompt(self, player_id: PlayerId) -> str:
        """LLM に渡すシステムプロンプト（キャラクター・ルール固定。player_id は互換のため残す）。"""
        del player_id  # 現状は全プレイヤー同一システム文面
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
        hours = (self._tick * 5) % (24 * 60)
        h, m = divmod(hours, 60)
        time_label = f"深夜 {h}:{m:02d}" if h < 6 else f"{h}:{m:02d}"
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
        """グラフ集約からイベントを収集し、観測パイプラインを通して各プレイヤーに配信する。"""
        from datetime import datetime
        graph = self._spot_graph_repo.find_graph()
        events = graph.get_events()
        graph.clear_events()
        now = datetime.now()
        hours = (self._tick * 5) % (24 * 60)
        h, m = divmod(hours, 60)
        time_label = f"深夜 {h}:{m:02d}" if h < 6 else f"{h}:{m:02d}"
        for event in events:
            items = self._obs_pipeline.run(event)
            for pid, output in items:
                entry = ObservationEntry(
                    occurred_at=now,
                    output=output,
                    game_time_label=time_label,
                )
                self._obs_buffer.append(pid, entry)

    def _record_action_result(
        self, player_id: PlayerId, action_summary: str, result_summary: str,
    ) -> None:
        from datetime import datetime
        self._action_result_store.append(
            player_id,
            action_summary=action_summary,
            result_summary=result_summary,
            occurred_at=datetime.now(),
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
        """LLM が memo_add で固定した未完了 memo を整形する。空なら ""。"""
        entries = self._todo_store.list_uncompleted(player_id)
        if not entries:
            return ""
        current_tick = self.current_tick()
        lines: List[str] = []
        for memo in entries:
            stale_prefix = ""
            age_part = ""
            if memo.added_at_tick is not None:
                elapsed = max(0, current_tick - memo.added_at_tick)
                age_part = f", 経過 {elapsed} tick"
                if elapsed >= stale_age_ticks:
                    stale_prefix = "[STALE] "
            tick_part = (
                f"tick={memo.added_at_tick}"
                if memo.added_at_tick is not None
                else memo.added_at.strftime("%H:%M")
            )
            lines.append(
                f"- {stale_prefix}[{tick_part}{age_part}] {memo.content} (id: {memo.id})"
            )
        return "\n".join(lines)

    # ── 完全プロンプト構築 ──

    _ESCAPE_GAME_OBJECTIVE_TEXT = (
        "- この廃墟から外へ脱出する。\n"
        "- 必要なら手がかり（物証・記録）を集め、判断材料にする。"
    )
    _ESCAPE_GAME_ACTION_INSTRUCTION = (
        "利用可能なツールから、次に取るべき 1 つの行動だけを選んでください。"
    )

    def build_full_prompt(self, player_id: PlayerId) -> dict:
        """各プレイヤーが LLM ターンで実際に受け取る完全なプロンプトを構築する。

        Issue #227 chore β: section 組み立ては本家
        ``SectionBasedContextFormatStrategy`` に委譲する。形式・順序の二重管理
        による drift を防ぐ。format 仕様は ``context_format_strategy.py`` 側に
        集約されているので、変更時はそちらを編集する。
        """
        self._wire_auxiliary_tool_stack()
        self._drain_buffer_to_sliding_window(player_id)

        ctx = self.build_llm_context(player_id)
        current_state_text = ctx.current_state_text

        recent_obs = self._sliding_window.get_recent(player_id, 20)
        recent_acts = self._action_result_store.get_recent(player_id, 20)
        recent_fmt = DefaultRecentEventsFormatter()
        recent_events_text = recent_fmt.format(recent_obs, recent_acts)

        inventory_block = self._format_inventory_evidence(player_id)
        active_memos_block = self._format_active_memos(player_id)

        # chore β: section 組み立てを本家 strategy に委譲
        context_strategy = SectionBasedContextFormatStrategy()
        context_body = context_strategy.format(
            current_state_text=current_state_text,
            recent_events_text=recent_events_text,
            relevant_memories_text="",  # episodic recall は未配線 (#240 で説明)
            active_memos_text=active_memos_block,
            objective_text=self._ESCAPE_GAME_OBJECTIVE_TEXT,
            inventory_text=inventory_block,
        )
        user_content = context_body + "\n\n" + self._ESCAPE_GAME_ACTION_INSTRUCTION

        system_content = self.build_system_prompt(player_id)
        return {
            "system": system_content,
            "user": user_content,
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
        recipients = self._scenario_event_recipients(event)
        time_label = self._time_label()
        for player_id in recipients:
            self._obs_buffer.append(
                player_id,
                ObservationEntry(
                    occurred_at=datetime.now(),
                    output=ObservationOutput(
                        prose=message,
                        structured={
                            "type": "scenario_event",
                            "event_id": event.event_id,
                            "message": message,
                        },
                        observation_category=event.observation_category,  # type: ignore[arg-type]
                        schedules_turn=event.schedules_turn,
                        breaks_movement=event.breaks_movement,
                    ),
                    game_time_label=time_label,
                ),
            )

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
        message = f"外の天候が変わった: {weather_state.weather_type.value}（強度 {weather_state.intensity:.1f}）"
        for player_id in self.get_player_ids():
            self._obs_buffer.append(
                player_id,
                ObservationEntry(
                    occurred_at=datetime.now(),
                    output=ObservationOutput(
                        prose=message,
                        structured={
                            "type": "weather_changed",
                            "weather_type": weather_state.weather_type.value,
                            "intensity": weather_state.intensity,
                        },
                        observation_category="environment",
                        schedules_turn=True,
                        breaks_movement=False,
                    ),
                    game_time_label=self._time_label(),
                ),
            )

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
    player_name_map = {spawn.player_id: spawn.name for spawn in scenario.player_spawns}

    def _resolve_entity_name(entity_id: int) -> str:
        return player_name_map.get(entity_id, f"プレイヤー({entity_id})")

    def _build_inventory(pid: PlayerId) -> tuple:
        inv = player_inventory_repo.find_by_id(pid)
        if inv is None:
            return ()
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
                seen_specs[sid] = [name, 0]
            seen_specs[sid][1] += 1
        return tuple(
            SpotGraphInventoryItemEntry(item_spec_id=sid, name=info[0], quantity=info[1])
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
    )

    # ── 観測パイプライン構築 ──
    # Issue #227 修正: 以前は SpotGraphRecipientStrategy 1 つだけで構築していた
    # ため、PlayerSpokeEvent / ConsumableUsedEvent / Conversation 系の event が
    # 配信先解決されずに silent drop していた。本家経路と同じ全 strategy 構成
    # を使うことで、event 種別ごとに正しい配信先 (距離 gating / 音透過 / target
    # 限定など) が機能する。
    #
    # physical_map_repository は 2d tile map 専用 strategy (Pursuit/Combat/
    # Monster/Default の世界座標フォールバック) の依存だが、escape_game は
    # spot_graph 専用で tile-map event は発火しないため、空の in-memory repo
    # で十分。SpotGraph 系 strategy が先に登録され、PlayerSpokeEvent は
    # SpotGraphSpeechRecipientStrategy (hop-based) で処理される。
    empty_physical_map_repo = InMemoryPhysicalMapRepository(data_store=data_store)
    obs_resolver = create_observation_recipient_resolver(
        player_status_repository=player_status_repo,
        physical_map_repository=empty_physical_map_repo,
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
    simulation_service = SpotGraphSimulationApplicationService(
        time_provider=time_provider,
        unit_of_work=InMemoryUnitOfWork(),
        travel_stage=travel_stage,
        scenario_event_stage=scenario_event_stage,
        reactive_binding_stage=reactive_binding_stage,
        reactive_object_state_stage=reactive_object_state_stage,
        sync_action_resolver_stage=sync_resolver_stage,
        environment_stage=environment_stage,
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
        _escape_llm_system_prompt=system_prompt_text,
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
    # を pipeline へ流す」publisher に置き換える。
    observation_appender = ObservationAppender(buffer=obs_buffer)

    class _PipelineEventPublisher(EventPublisher[DomainEvent]):
        """全 DomainEvent を ObservationPipeline 経由で配信する EventPublisher。

        register_handler は no-op (per-event-type 登録は使わない)。publish /
        publish_all / publish_async_events はいずれも _dispatch に集約し、
        pipeline.run → appender.append → scheduler.maybe_schedule を実行する。
        """

        def __init__(self, runtime_ref: "EscapeGameRuntime") -> None:
            self._runtime = runtime_ref

        def register_handler(
            self,
            event_type,
            handler,
            is_synchronous: bool = False,
        ) -> None:
            del event_type, handler, is_synchronous

        def publish(self, event: DomainEvent) -> None:
            self._dispatch(event)

        def publish_all(self, events) -> None:
            for event in events:
                self._dispatch(event)

        def publish_async_events(self, events) -> None:
            for event in events:
                self._dispatch(event)

        def _dispatch(self, event: DomainEvent) -> None:
            items = self._runtime._obs_pipeline.run(event)
            if not items:
                return
            # PR 7 (#227 review HIGH 1): production code に assert は不可
            # (python -O で評価されなくなる)。observation_appender は通常
            # create_escape_game_runtime の末尾で設定されるが、構築途中で
            # publisher 経由のイベントが入った場合に備えて静かに skip する。
            appender = self._runtime._observation_appender
            if appender is None:
                return
            now = datetime.now()
            time_label = self._runtime._time_label()
            for pid, output in items:
                appender.append(pid, output, now, time_label)
                scheduler = self._runtime._observation_turn_scheduler
                if scheduler is not None:
                    scheduler.maybe_schedule(pid, output)

    pipeline_event_publisher = _PipelineEventPublisher(runtime)
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
    interaction_service._event_publisher = pipeline_event_publisher

    runtime._speech_service = speech_service
    runtime._speech_event_publisher = pipeline_event_publisher
    runtime._observation_appender = observation_appender

    return runtime
