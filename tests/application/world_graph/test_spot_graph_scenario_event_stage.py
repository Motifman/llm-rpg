from __future__ import annotations

from ai_rpg_world.application.world_graph.spot_graph_scenario_event_progress_store import (
    InMemorySpotGraphScenarioEventProgressStore,
)
from ai_rpg_world.application.world_graph.spot_graph_scenario_event_stage_service import (
    SpotGraphScenarioEventStageService,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import PlayerStatusAggregate
from ai_rpg_world.domain.player.value_object.base_stats import BaseStats
from ai_rpg_world.domain.player.value_object.exp_table import ExpTable
from ai_rpg_world.domain.player.value_object.gold import Gold
from ai_rpg_world.domain.player.value_object.growth import Growth
from ai_rpg_world.domain.player.value_object.hp import Hp
from ai_rpg_world.domain.player.value_object.mp import Mp
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.player_spot_navigation_state import (
    PlayerSpotNavigationState,
)
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import InMemoryItemRepository
from ai_rpg_world.infrastructure.repository.in_memory_item_spec_repository import (
    InMemoryItemSpecRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_inventory_repository import (
    InMemoryPlayerInventoryRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_player_status_repository import (
    InMemoryPlayerStatusRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_graph_repository import (
    InMemorySpotGraphRepository,
)
from ai_rpg_world.infrastructure.repository.in_memory_spot_interior_repository import (
    InMemorySpotInteriorRepository,
)
from ai_rpg_world.infrastructure.scenario.scenario_loader import ScenarioLoader


def _minimal_scenario_with_tick_event() -> dict:
    return {
        "scenario_format_version": "1.0",
        "metadata": {"id": "test", "title": "t", "description": "", "theme": "", "difficulty": "easy", "estimated_ticks": 10, "author": "", "tags": []},
        "item_specs": [],
        "spots": [
            {
                "id": "room_a",
                "name": "部屋A",
                "description": "A",
                "interior": {"objects": []},
            }
        ],
        "connections": [],
        "players": [{"id": "p1", "name": "P1", "spawn_spot": "room_a", "initial_items": []}],
        "game_end_conditions": {"win": {"type": "ALL_AT_SPOT", "target_spot": "room_a"}, "lose": {"type": "TICK_LIMIT", "tick_limit": 50}},
        "initial_flags": [],
        "scenario_events": [
            {
                "id": "ev1",
                "trigger": "ON_TICK",
                "once": True,
                "conditions": [{"condition_type": "TICK_AT_LEAST", "tick": 2}],
                "effects": [
                    {"effect_type": "SHOW_MESSAGE", "parameters": {"message": "event fired"}},
                    {"effect_type": "SET_FLAG", "parameters": {"flag_name": "ev1_done"}},
                ],
            }
        ],
    }


def _build_player_status(pid: PlayerId, spawn_spot_id) -> PlayerStatusAggregate:
    exp_table = ExpTable(base_exp=100.0, exponent=1.5)
    return PlayerStatusAggregate(
        player_id=pid,
        base_stats=BaseStats(max_hp=100, max_mp=50, attack=10, defense=10, speed=10, critical_rate=0.05, evasion_rate=0.05),
        stat_growth_factor=StatGrowthFactor(hp_factor=1.0, mp_factor=1.0, attack_factor=1.0, defense_factor=1.0, speed_factor=1.0, critical_rate_factor=0.0, evasion_rate_factor=0.0),
        exp_table=exp_table,
        growth=Growth(level=1, total_exp=0, exp_table=exp_table),
        gold=Gold(0),
        hp=Hp(value=100, max_hp=100),
        mp=Mp(value=50, max_mp=50),
        stamina=Stamina(value=100, max_stamina=100),
        spot_navigation_state=PlayerSpotNavigationState.at_rest(spawn_spot_id),
    )


def test_scenario_event_stage_fires_once_and_sets_flag() -> None:
    loaded = ScenarioLoader().load_from_dict(_minimal_scenario_with_tick_event())
    data_store = InMemoryDataStore()
    spot_graph_repo = InMemorySpotGraphRepository(loaded.graph)
    spot_interior_repo = InMemorySpotInteriorRepository()
    for sid, interior in loaded.interiors.items():
        spot_interior_repo.save(sid, interior)
    player_status_repo = InMemoryPlayerStatusRepository(data_store)
    player_inventory_repo = InMemoryPlayerInventoryRepository(data_store)
    item_repo = InMemoryItemRepository(data_store)
    item_spec_repo = InMemoryItemSpecRepository()
    spawn = loaded.player_spawns[0]
    pid = PlayerId(spawn.player_id)
    player_status_repo.save(_build_player_status(pid, spawn.spawn_spot_id))
    player_inventory_repo.save(PlayerInventoryAggregate(player_id=pid))
    world_flags = MutableWorldFlagState()
    progress = InMemorySpotGraphScenarioEventProgressStore()
    received: list[str] = []
    stage = SpotGraphScenarioEventStageService(
        scenario_events=loaded.scenario_events,
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        player_status_repository=player_status_repo,
        player_inventory_repository=player_inventory_repo,
        item_repository=item_repo,
        item_spec_repository=item_spec_repo,
        world_flag_state=world_flags,
        progress_store=progress,
        on_message=lambda event, message: received.append(message),
    )

    stage.run(WorldTick(1))
    assert "ev1_done" not in world_flags.as_frozen_set()

    stage.run(WorldTick(2))
    assert "ev1_done" in world_flags.as_frozen_set()
    assert received == ["event fired"]
    assert progress.is_fired("ev1")

    stage.run(WorldTick(3))
    assert received == ["event fired"]


def _scenario_with_composite_condition(condition: dict) -> dict:
    """与えた condition を ev1 に持つ最小シナリオを返す。"""
    scn = _minimal_scenario_with_tick_event()
    scn["scenario_events"][0]["conditions"] = [condition]
    return scn


def _make_stage_for_scenario(scn: dict, *, initial_flags: list[str] | None = None):
    """共通セットアップ。stage と world_flags、received list を返す。"""
    loaded = ScenarioLoader().load_from_dict(scn)
    data_store = InMemoryDataStore()
    spot_graph_repo = InMemorySpotGraphRepository(loaded.graph)
    spot_interior_repo = InMemorySpotInteriorRepository()
    for sid, interior in loaded.interiors.items():
        spot_interior_repo.save(sid, interior)
    player_status_repo = InMemoryPlayerStatusRepository(data_store)
    player_inventory_repo = InMemoryPlayerInventoryRepository(data_store)
    item_repo = InMemoryItemRepository(data_store)
    item_spec_repo = InMemoryItemSpecRepository()
    spawn = loaded.player_spawns[0]
    pid = PlayerId(spawn.player_id)
    player_status_repo.save(_build_player_status(pid, spawn.spawn_spot_id))
    player_inventory_repo.save(PlayerInventoryAggregate(player_id=pid))
    world_flags = MutableWorldFlagState()
    if initial_flags:
        for f in initial_flags:
            world_flags.add(f)
    progress = InMemorySpotGraphScenarioEventProgressStore()
    received: list[str] = []
    stage = SpotGraphScenarioEventStageService(
        scenario_events=loaded.scenario_events,
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=spot_interior_repo,
        player_status_repository=player_status_repo,
        player_inventory_repository=player_inventory_repo,
        item_repository=item_repo,
        item_spec_repository=item_spec_repo,
        world_flag_state=world_flags,
        progress_store=progress,
        on_message=lambda event, message: received.append(message),
    )
    return stage, world_flags, received


class TestCompositeConditionEvaluation:
    """NOT / AND / OR 合成条件の評価が ScenarioEventStageService で正しく動く。"""

    def test_not_fires_when_inner_condition_is_false(self) -> None:
        """NOT(FLAG_SET) は flag が無いときに発火する。"""
        scn = _scenario_with_composite_condition({
            "condition_type": "NOT",
            "children": [{"condition_type": "FLAG_SET", "flag_name": "blocker"}],
        })
        stage, flags, _ = _make_stage_for_scenario(scn)
        stage.run(WorldTick(1))
        assert "ev1_done" in flags.as_frozen_set()

    def test_not_does_not_fire_when_inner_condition_is_true(self) -> None:
        """NOT(FLAG_SET) は flag があれば発火しない。"""
        scn = _scenario_with_composite_condition({
            "condition_type": "NOT",
            "children": [{"condition_type": "FLAG_SET", "flag_name": "blocker"}],
        })
        stage, flags, _ = _make_stage_for_scenario(scn, initial_flags=["blocker"])
        stage.run(WorldTick(1))
        assert "ev1_done" not in flags.as_frozen_set()

    def test_and_requires_all_children(self) -> None:
        """AND は全子条件が真でないと発火しない。"""
        scn = _scenario_with_composite_condition({
            "condition_type": "AND",
            "children": [
                {"condition_type": "TICK_AT_LEAST", "tick": 2},
                {"condition_type": "FLAG_SET", "flag_name": "ready"},
            ],
        })
        stage, flags, _ = _make_stage_for_scenario(scn)
        # tick 満たすが flag 未設定 → 発火しない
        stage.run(WorldTick(2))
        assert "ev1_done" not in flags.as_frozen_set()

    def test_and_fires_when_all_children_true(self) -> None:
        """AND は全子条件が真なら発火する。"""
        scn = _scenario_with_composite_condition({
            "condition_type": "AND",
            "children": [
                {"condition_type": "TICK_AT_LEAST", "tick": 2},
                {"condition_type": "FLAG_SET", "flag_name": "ready"},
            ],
        })
        stage, flags, _ = _make_stage_for_scenario(scn, initial_flags=["ready"])
        stage.run(WorldTick(2))
        assert "ev1_done" in flags.as_frozen_set()

    def test_or_fires_when_any_child_true(self) -> None:
        """OR はどれか 1 つでも子条件が真なら発火する。"""
        scn = _scenario_with_composite_condition({
            "condition_type": "OR",
            "children": [
                {"condition_type": "FLAG_SET", "flag_name": "alpha"},
                {"condition_type": "FLAG_SET", "flag_name": "beta"},
            ],
        })
        stage, flags, _ = _make_stage_for_scenario(scn, initial_flags=["beta"])
        stage.run(WorldTick(1))
        assert "ev1_done" in flags.as_frozen_set()

    def test_or_does_not_fire_when_all_children_false(self) -> None:
        """OR は全子条件が偽なら発火しない。"""
        scn = _scenario_with_composite_condition({
            "condition_type": "OR",
            "children": [
                {"condition_type": "FLAG_SET", "flag_name": "alpha"},
                {"condition_type": "FLAG_SET", "flag_name": "beta"},
            ],
        })
        stage, flags, _ = _make_stage_for_scenario(scn)
        stage.run(WorldTick(1))
        assert "ev1_done" not in flags.as_frozen_set()

    def test_nested_composite_de_morgan(self) -> None:
        """NOT(OR(A,B)) と AND(NOT(A), NOT(B)) が同じ評価結果になる。"""
        scn = _scenario_with_composite_condition({
            "condition_type": "AND",
            "children": [
                {"condition_type": "NOT", "children": [
                    {"condition_type": "FLAG_SET", "flag_name": "a"},
                ]},
                {"condition_type": "NOT", "children": [
                    {"condition_type": "FLAG_SET", "flag_name": "b"},
                ]},
            ],
        })
        # どちらも未設定 → 発火する
        stage, flags, _ = _make_stage_for_scenario(scn)
        stage.run(WorldTick(1))
        assert "ev1_done" in flags.as_frozen_set()
