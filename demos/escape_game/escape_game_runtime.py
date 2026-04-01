"""廃病院脱出ゲームのランタイム。

シナリオ JSON → インメモリリポジトリ → アプリケーションサービス をワイヤリングし、
プログラム的にアクションを実行できるようにする。

LLM エージェントが**実際に**受け取る観測テキスト・ツール定義・ラベル解決コンテキストを
そのまま可視化する。デモ専用の加工は行わない。
"""

from __future__ import annotations

import json
import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

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
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.application.world_graph.spot_graph_current_state_builder import (
    SpotGraphCurrentStateBuilder,
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
    LlmUiContextDto,
    ToolDefinitionDto,
    ToolRuntimeContextDto,
)
from ai_rpg_world.application.llm.services.tool_catalog.spot_graph import get_spot_graph_specs

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
    _tick: int = 0

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
        return self._tick

    def advance_tick(self) -> int:
        self._tick += 1
        return self._tick

    # ── 後方互換ヘルパー（テスト用） ──

    def build_observation(self, player_id: PlayerId) -> str:
        """E2E テスト用の簡易観測テキスト。build_llm_context のテキスト部分を返す。"""
        return self.build_llm_context(player_id).current_state_text

    def build_available_tools(self, player_id: PlayerId) -> str:
        """E2E テスト用のツール一覧テキスト。"""
        names = [d.name for d in self.get_tool_definitions()]
        return ", ".join(names)

    def build_system_prompt(self, player_id: PlayerId) -> str:
        """E2E テスト用のシステムプロンプト概要テキスト。"""
        m = self.metadata
        return (
            f"あなたは「{m.title}」の探索者です。\n"
            f"テーマ: {m.theme}\n"
            f"推定ティック: {m.estimated_ticks}\n"
            f"説明: {m.description}"
        )

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
        )

    def get_tool_definitions(self) -> List[ToolDefinitionDto]:
        """LLM に渡されるツール定義（OpenAI tools 形式）を返す。"""
        return [defn for defn, _ in get_spot_graph_specs()]

    # ── アクション実行 ──

    def do_interact(
        self, player_id: PlayerId, object_str_id: str, action_name: str,
    ) -> SpotInteractionResultDto:
        obj_int = self.id_mapper.get_int("object", object_str_id)
        result = self._interaction_service.execute_interaction(
            player_id, SpotObjectId.create(obj_int), action_name,
        )
        return result

    def do_explore(self, player_id: PlayerId) -> SpotExplorationResultDto:
        result = self._exploration_service.explore_once(player_id)
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
        for _ in range(20):
            adv = self._movement_service.advance_spot_travel_one_tick(player_id, owned, flags)
            self._tick += 1
            if adv is None:
                break

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


def create_escape_game_runtime(scenario_path: Path) -> EscapeGameRuntime:
    """シナリオ JSON からゲームランタイムを構築する。"""
    loader = ScenarioLoader()
    scenario = loader.load_from_file(scenario_path)

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
    state_builder = SpotGraphCurrentStateBuilder(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        player_status_repository=player_status_repo,
    )

    return EscapeGameRuntime(
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
    )
