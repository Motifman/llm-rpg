"""廃病院脱出ゲームのランタイム。

シナリオ JSON → インメモリリポジトリ → アプリケーションサービス をワイヤリングし、
プログラム的にアクションを実行できるようにする。

LLM エージェントが**実際に**受け取る観測テキスト・ツール定義・ラベル解決コンテキストを
そのまま可視化する。デモ専用の加工は行わない。
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Tuple

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
from ai_rpg_world.domain.player.value_object.player_spot_navigation_state import PlayerSpotNavigationState
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
from ai_rpg_world.application.llm.services.recent_events_formatter import DefaultRecentEventsFormatter
from ai_rpg_world.application.llm.services.memory_extractor import RuleBasedMemoryExtractor
from ai_rpg_world.application.llm.services.memory_query_executor import MemoryQueryExecutor
from ai_rpg_world.application.llm.services.in_memory_episode_memory_store import (
    InMemoryEpisodeMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_long_term_memory_store import (
    InMemoryLongTermMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_working_memory_store import (
    InMemoryWorkingMemoryStore,
)
from ai_rpg_world.application.llm.services.in_memory_todo_store import InMemoryTodoStore
from ai_rpg_world.application.llm.services.handle_store import InMemoryHandleStore
from ai_rpg_world.application.llm.services.executors.memory_executor import MemoryToolExecutor
from ai_rpg_world.application.llm.services.executors.todo_executor import TodoToolExecutor
from ai_rpg_world.application.llm.services.escape_llm_prompt import (
    EscapeCharacterPromptInput,
    build_escape_system_prompt,
    build_persona_block_from_escape_character,
    format_episode_snippets_for_prompt,
    format_working_memory_for_prompt,
    safe_world_intro_text,
    suggest_next_actions_from_targets,
)
from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry, ObservationOutput
from ai_rpg_world.application.observation.services.observation_context_buffer import DefaultObservationContextBuffer
from ai_rpg_world.application.observation.services.observation_pipeline import ObservationPipeline
from ai_rpg_world.application.observation.services.observation_formatter import ObservationFormatter
from ai_rpg_world.application.observation.services.observation_recipient_resolver import ObservationRecipientResolver
from ai_rpg_world.application.observation.services.observed_event_registry import ObservedEventRegistry
from ai_rpg_world.application.observation.services.recipient_strategies.spot_graph_recipient_strategy import SpotGraphRecipientStrategy

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
    _memory_overflow_for_next_commit: Dict[int, List[ObservationEntry]] = field(
        default_factory=dict, repr=False
    )
    _episode_memory_store: InMemoryEpisodeMemoryStore = field(
        default_factory=InMemoryEpisodeMemoryStore, repr=False
    )
    _long_term_memory_store: InMemoryLongTermMemoryStore = field(
        default_factory=InMemoryLongTermMemoryStore, repr=False
    )
    _working_memory_store: InMemoryWorkingMemoryStore = field(
        default_factory=InMemoryWorkingMemoryStore, repr=False
    )
    _todo_store: InMemoryTodoStore = field(default_factory=InMemoryTodoStore, repr=False)
    _handle_store: InMemoryHandleStore = field(default_factory=InMemoryHandleStore, repr=False)
    _memory_query_executor: Optional[MemoryQueryExecutor] = field(default=None, repr=False)
    _memory_tool_executor: Optional[MemoryToolExecutor] = field(default=None, repr=False)
    _todo_tool_executor: Optional[TodoToolExecutor] = field(default=None, repr=False)
    _memory_extractor: RuleBasedMemoryExtractor = field(
        default_factory=RuleBasedMemoryExtractor, repr=False
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
        )

    def get_tool_definitions(self) -> List[ToolDefinitionDto]:
        """LLM に渡されるツール定義（OpenAI tools 形式）を返す。"""
        spot = [defn for defn, _ in get_spot_graph_specs()]
        memory = [
            defn
            for defn, _ in get_memory_specs(
                memory_query_enabled=True,
                subagent_enabled=False,
                todo_enabled=True,
                working_memory_enabled=True,
            )
        ]
        return spot + memory

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
        self._maybe_extract_episode(player_id, action_summary, result_summary)

    def _drain_buffer_to_sliding_window(self, player_id: PlayerId) -> List[ObservationEntry]:
        """観測バッファをスライディングウィンドウに移す。溢れた観測を返す。"""
        drained = self._obs_buffer.drain(player_id)
        if not drained:
            return []
        return self._sliding_window.append_all(player_id, drained)

    def _wire_memory_stack(self) -> None:
        """MemoryQueryExecutor とツール実行器を遅延初期化する。"""
        if self._memory_query_executor is not None:
            return

        recent_fmt = DefaultRecentEventsFormatter()

        def state_provider(pid: PlayerId) -> str:
            return self.build_llm_context(pid).current_state_text

        self._memory_query_executor = MemoryQueryExecutor(
            episode_store=self._episode_memory_store,
            long_term_store=self._long_term_memory_store,
            sliding_window=self._sliding_window,
            action_result_store=self._action_result_store,
            working_memory_store=self._working_memory_store,
            state_provider=state_provider,
            recent_events_formatter=recent_fmt,
            handle_store=self._handle_store,
        )
        self._memory_tool_executor = MemoryToolExecutor(
            memory_query_executor=self._memory_query_executor,
            subagent_runner=None,
            working_memory_store=self._working_memory_store,
        )
        self._todo_tool_executor = TodoToolExecutor(self._todo_store)

    def run_llm_auxiliary_tool(
        self, player_id: PlayerId, name: str, arguments: Dict[str, Any]
    ) -> LlmCommandResultDto:
        """memory_query / working_memory_append / TODO 系ツールを実行する。"""
        self._wire_memory_stack()
        assert self._memory_tool_executor is not None
        assert self._todo_tool_executor is not None
        handlers: Dict[str, Callable[[int, Dict[str, Any]], LlmCommandResultDto]] = {}
        handlers.update(self._memory_tool_executor.get_handlers())
        handlers.update(self._todo_tool_executor.get_handlers())
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

    def _format_long_term_snippets(self, player_id: PlayerId, keyword: str) -> str:
        kws = [keyword] if keyword.strip() else None
        facts = self._long_term_memory_store.search_facts(player_id, keywords=kws, limit=5)
        if not facts:
            return "（長期メモに登録された事実はまだ少ない）"
        return "\n".join(f"- {f.content[:200]}" for f in facts)

    def _maybe_extract_episode(
        self,
        player_id: PlayerId,
        action_summary: str,
        result_summary: str,
    ) -> None:
        overflow = self._memory_overflow_for_next_commit.pop(player_id.value, [])
        episodes = self._memory_extractor.extract(
            player_id, overflow, action_summary, result_summary
        )
        if not episodes:
            return
        self._episode_memory_store.add_many(player_id, episodes)

    # ── 完全プロンプト構築 ──

    def build_full_prompt(self, player_id: PlayerId) -> dict:
        """各プレイヤーが LLM ターンで実際に受け取る完全なプロンプトを構築する。"""
        self._wire_memory_stack()
        evicted = self._drain_buffer_to_sliding_window(player_id)
        self._memory_overflow_for_next_commit[player_id.value] = evicted

        ctx = self.build_llm_context(player_id)
        current_state_text = ctx.current_state_text

        recent_obs = self._sliding_window.get_recent(player_id, 20)
        recent_acts = self._action_result_store.get_recent(player_id, 20)
        recent_fmt = DefaultRecentEventsFormatter()
        recent_events_text = recent_fmt.format(recent_obs, recent_acts)

        snap = self._state_builder.build_snapshot(int(player_id))
        spot_kw = (snap.current_spot_name or "").strip() if snap is not None else ""

        episodes = self._episode_memory_store.get_recent(player_id, 8)
        related_mem = format_episode_snippets_for_prompt(episodes, limit=5)
        wm_texts = self._working_memory_store.get_recent(player_id, 12)
        hypothesis_block = format_working_memory_for_prompt(wm_texts, limit=8)
        long_term_block = self._format_long_term_snippets(player_id, spot_kw)
        targets = getattr(ctx.tool_runtime_context, "targets", {}) or {}
        next_hints = suggest_next_actions_from_targets(targets)
        inventory_block = self._format_inventory_evidence(player_id)

        user_content = "\n".join(
            [
                "【現在の目的】",
                "- この廃墟から外へ脱出する。",
                "- 必要なら手がかり（物証・記録）を集め、判断材料にする。",
                "",
                "【現在地と周囲】",
                current_state_text.strip() or "（情報なし）",
                "",
                "【直近の出来事】",
                recent_events_text.strip() or "（なし）",
                "",
                "【発見済み証拠（所持・判明した物証）】",
                inventory_block,
                "",
                "【未解決の仮説・作業メモ】",
                hypothesis_block,
                "",
                "【長期メモ（事実の抜粋）】",
                long_term_block,
                "",
                "【関連する記憶（想起）】",
                related_mem,
                "",
                "【次に試せそうなこと（候補）】",
                next_hints,
                "",
                "利用可能なツールから、次に取るべき 1 つの行動だけを選んでください。",
            ]
        )

        system_content = self.build_system_prompt(player_id)
        return {
            "system": system_content,
            "user": user_content,
            "tools": [d.name for d in self.get_tool_definitions()],
            "tool_runtime_context": ctx.tool_runtime_context,
        }

    # ── アクション実行 ──

    def do_interact(
        self, player_id: PlayerId, object_str_id: str, action_name: str,
    ) -> SpotInteractionResultDto:
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import SpotObjectInteractedEvent
        obj_int = self.id_mapper.get_int("object", object_str_id)
        obj_id = SpotObjectId.create(obj_int)
        graph = self._spot_graph_repo.find_graph()
        eid = EntityId.create(int(player_id))
        spot_id = graph.get_entity_spot(eid)
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
        self._record_action_result(player_id, f"interact({object_str_id}, {action_name})", result_text)
        return result

    def do_explore(self, player_id: PlayerId) -> SpotExplorationResultDto:
        from ai_rpg_world.domain.world_graph.event.spot_graph_event import SpotExploredEvent
        graph = self._spot_graph_repo.find_graph()
        eid = EntityId.create(int(player_id))
        spot_id = graph.get_entity_spot(eid)
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
        result_text = f"発見: {', '.join(result.discovery_descriptions)}" if result.discovery_descriptions else "新しい発見はなかった"
        self._record_action_result(player_id, "explore_sub_locations()", result_text)
        return result

    def do_move(self, player_id: PlayerId, dest_spot_str_id: str) -> None:
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
        self._record_action_result(player_id, f"travel_to({dest_spot_str_id})", f"{dest_name}に到着した")

    def do_wait(self, player_id: PlayerId, reason: str = "") -> int:
        tick = self.advance_tick()
        note = f"wait({reason})" if reason else "wait()"
        self._record_action_result(player_id, note, f"時間が進んだ（tick={tick}）")
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


def _escape_llm_ssot_enabled_from_env() -> bool:
    """環境変数 ESCAPE_LLM_SSOT が 1/true/yes/on のいずれかなら SSoT を有効にする。"""
    v = os.environ.get("ESCAPE_LLM_SSOT", "").strip().lower()
    return v in ("1", "true", "yes", "on")


def create_escape_game_runtime(
    scenario_path: Path,
    *,
    escape_character: Optional[EscapeCharacterPromptInput] = None,
) -> EscapeGameRuntime:
    """シナリオ JSON からゲームランタイムを構築する。"""
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
    participants = tuple(s.name for s in scenario.player_spawns)
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
        )
        item_spec_repo.save(spec)

    player_status_repo = InMemoryPlayerStatusRepository(data_store)
    player_inventory_repo = InMemoryPlayerInventoryRepository(data_store)

    graph = spot_graph_repo.find_graph()
    for spawn in scenario.player_spawns:
        pid = PlayerId(spawn.player_id)
        exp_table = ExpTable(base_exp=100.0, exponent=1.5)
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

    state_builder = SpotGraphCurrentStateBuilder(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        player_status_repository=player_status_repo,
        entity_name_resolver=_resolve_entity_name,
        inventory_builder=_build_inventory,
        weather_provider=lambda: weather_holder["state"],
        world_flags_provider=world_flag_state.as_frozen_set,
    )

    # ── 観測パイプライン構築 ──
    registry = ObservedEventRegistry()
    spot_graph_strategy = SpotGraphRecipientStrategy(
        observed_event_registry=registry,
        spot_graph_repository=spot_graph_repo,
        player_status_repository=player_status_repo,
    )
    obs_resolver = ObservationRecipientResolver(strategies=[spot_graph_strategy])

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
    simulation_service = SpotGraphSimulationApplicationService(
        time_provider=time_provider,
        unit_of_work=InMemoryUnitOfWork(),
        travel_stage=travel_stage,
        scenario_event_stage=scenario_event_stage,
        environment_stage=environment_stage,
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
    )
    scenario_event_stage.set_message_callback(
        runtime._append_scenario_event_observation
    )
    if weather_config is None or weather_config.announce_changes:
        environment_stage.set_weather_changed_callback(runtime._append_weather_observation)
    return runtime
