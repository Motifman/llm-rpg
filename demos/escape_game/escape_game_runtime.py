"""廃病院脱出ゲームのランタイム。

シナリオ JSON → インメモリリポジトリ → アプリケーションサービス をワイヤリングし、
プログラム的にアクションを実行できるようにする。

LLM エージェントが受け取る観測テキストと、利用可能なツール一覧を可視化する。
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, FrozenSet, List, Optional, Tuple

from ai_rpg_world.domain.item.read_model.item_spec_read_model import ItemSpecReadModel
from ai_rpg_world.domain.item.value_object.item_spec import ItemSpec
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import PlayerInventoryAggregate
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
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
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_interior import SpotInterior
from ai_rpg_world.domain.world_graph.service.game_end_condition_evaluator import GameEndConditionEvaluator
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.game_end_condition import GameEndCondition
from ai_rpg_world.domain.world_graph.value_object.game_end_result import GameEndResult
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.domain.world_graph.value_object.world_flag_registry import WorldFlagRegistry

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
from ai_rpg_world.application.world_graph.spot_graph_current_state_dtos import (
    SpotGraphPlayerSnapshotDto,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    collect_owned_item_spec_ids_from_inventory,
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


@dataclass
class ActionRecord:
    """実行されたアクションの記録。"""
    tick: int
    player_name: str
    action_type: str
    action_detail: str
    result_messages: Tuple[str, ...]
    observation_after: str


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
    _tick: int = 0
    history: List[ActionRecord] = field(default_factory=list)

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

    # ── 観測（LLM が受け取るテキスト）──

    def build_observation(self, player_id: PlayerId) -> str:
        snap = self._state_builder.build_snapshot(int(player_id))
        if snap is None:
            return "(このプレイヤーはまだグラフ上に配置されていません)"
        return self._format_snapshot(snap, player_id)

    def _format_snapshot(self, snap: SpotGraphPlayerSnapshotDto, player_id: PlayerId) -> str:
        lines: List[str] = []
        lines.append(f"現在地: {snap.current_spot_name}")
        lines.append(f"  {snap.current_spot_description}")
        if snap.travel_status_line:
            lines.append(snap.travel_status_line)

        graph = self._spot_graph_repo.find_graph()
        eid = EntityId.create(int(player_id))
        spot_id = graph.get_entity_spot(eid)
        node = graph.get_spot(spot_id)
        if node.atmosphere:
            a = node.atmosphere
            atmo_parts = []
            atmo_parts.append(f"明るさ: {a.lighting.name}")
            if a.sound_ambient:
                atmo_parts.append(f"音: {a.sound_ambient}")
            atmo_parts.append(f"気温: {a.temperature.name}")
            if a.smell:
                atmo_parts.append(f"匂い: {a.smell}")
            lines.append("雰囲気: " + " / ".join(atmo_parts))

        others = []
        presence = graph.presence_at(spot_id)
        for other_eid in presence.present_entity_ids:
            if other_eid != eid:
                for p in self.scenario.player_spawns:
                    if int(other_eid) == p.player_id:
                        others.append(p.name)
        if others:
            lines.append(f"同じスポットにいる人: {', '.join(others)}")

        if snap.sub_location_lines:
            lines.append("サブロケーション:")
            lines.extend(f"  {x}" for x in snap.sub_location_lines)

        if snap.object_lines:
            lines.append("見えるオブジェクト:")
            lines.extend(f"  {x}" for x in snap.object_lines)

        if snap.ground_item_lines:
            lines.append("落ちているアイテム:")
            lines.extend(f"  {x}" for x in snap.ground_item_lines)

        if snap.connection_lines:
            lines.append("接続先:")
            lines.extend(f"  {x}" for x in snap.connection_lines)

        inv = self._player_inventory_repo.find_by_id(player_id)
        if inv:
            item_names = self._list_inventory_item_names(inv)
            if item_names:
                lines.append("所持アイテム:")
                lines.extend(f"  - {n}" for n in item_names)
            else:
                lines.append("所持アイテム: なし")

        flags = self._world_flag_state.as_frozen_set()
        if flags:
            lines.append(f"ワールドフラグ: {', '.join(sorted(flags))}")

        lines.append(f"現在ティック: {self._tick}")
        return "\n".join(lines)

    def _list_inventory_item_names(self, inv: PlayerInventoryAggregate) -> List[str]:
        from ai_rpg_world.domain.player.value_object.slot_id import SlotId
        names = []
        for i in range(inv.max_slots):
            iid = inv.get_item_instance_id_by_slot(SlotId(i))
            if iid is None:
                continue
            item = self._item_repo.find_by_id(iid)
            if item:
                names.append(item.item_spec.name)
        return names

    # ── 利用可能ツール一覧（LLM が選択肢として受け取る）──

    def build_available_tools(self, player_id: PlayerId) -> str:
        graph = self._spot_graph_repo.find_graph()
        eid = EntityId.create(int(player_id))
        spot_id = graph.get_entity_spot(eid)
        interior = self._spot_interior_repo.find_by_spot_id(spot_id)

        tools: List[str] = []
        tools.append("=== 利用可能なツール ===")

        passable_conns = [
            c for c in graph.iter_outgoing_connections_from(spot_id) if c.is_passable
        ]
        for conn in passable_conns:
            dest = graph.get_spot(conn.to_spot_id)
            dest_str = self.id_mapper.get_str("spot", int(conn.to_spot_id.value))
            tools.append(
                f'spot_graph_travel_to(destination_spot_id={int(conn.to_spot_id.value)})  '
                f'# → {dest.name} ({dest_str})'
            )

        tools.append(f"spot_graph_explore()  # 現在のスポットを探索する")

        if interior:
            for obj in interior.objects:
                if not obj.is_visible:
                    continue
                for inter in obj.interactions:
                    obj_str = self.id_mapper.get_str("object", int(obj.object_id.value))
                    tools.append(
                        f'spot_graph_interact(object_id={int(obj.object_id.value)}, '
                        f'action_name="{inter.action_name}")  '
                        f'# {obj.name}: {inter.display_label} ({obj_str})'
                    )

        tools.append('speak(message="...")  # 同じスポットの人に話す')
        tools.append('shout(message="...")  # 周辺スポットにも届くように叫ぶ')

        return "\n".join(tools)

    # ── LLM システムプロンプト（可視化用）──

    def build_system_prompt(self, player_id: PlayerId) -> str:
        name = self.get_player_name(player_id)
        return textwrap.dedent(f"""\
            あなたは「{name}」として廃病院からの脱出ゲームに参加しています。

            【シナリオ】
            {self.metadata.description}

            【ルール】
            - 仲間と協力して廃病院から脱出してください
            - スポットを探索してアイテムや手がかりを見つけてください
            - オブジェクトを調べたり操作したりしてパズルを解いてください
            - 仲間と情報を共有するために speak や shout を使ってください
            - 制限ティック（{self.scenario.lose_conditions[0].tick_limit}）以内に全員が外に出れば勝利です

            【行動指針】
            毎ターン、現在の状況を確認し、最も有効だと思うアクションを1つ選んでください。
            アクションは利用可能なツールから選びます。""")

    # ── アクション実行 ──

    def do_interact(
        self, player_id: PlayerId, object_str_id: str, action_name: str,
    ) -> SpotInteractionResultDto:
        obj_int = self.id_mapper.get_int("object", object_str_id)
        result = self._interaction_service.execute_interaction(
            player_id, SpotObjectId.create(obj_int), action_name,
        )
        obs = self.build_observation(player_id)
        self.history.append(ActionRecord(
            tick=self._tick,
            player_name=self.get_player_name(player_id),
            action_type="interact",
            action_detail=f"{object_str_id}.{action_name}",
            result_messages=result.messages,
            observation_after=obs,
        ))
        return result

    def do_explore(self, player_id: PlayerId) -> SpotExplorationResultDto:
        result = self._exploration_service.explore_once(player_id)
        obs = self.build_observation(player_id)
        self.history.append(ActionRecord(
            tick=self._tick,
            player_name=self.get_player_name(player_id),
            action_type="explore",
            action_detail="explore_spot",
            result_messages=result.discovery_descriptions,
            observation_after=obs,
        ))
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
            if adv is None:
                break

        obs = self.build_observation(player_id)
        self.history.append(ActionRecord(
            tick=self._tick,
            player_name=self.get_player_name(player_id),
            action_type="move",
            action_detail=f"→ {dest_spot_str_id}",
            result_messages=(),
            observation_after=obs,
        ))

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
    )
