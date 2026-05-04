"""シナリオイベントのエスカレーション（チェーン発火 + tick_modulo）のテスト。

Phase 6: 環境変化のエスカレーション機能を検証する。
"""

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
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.interaction_effect import InteractionEffect
from ai_rpg_world.domain.world_graph.value_object.scenario_event_condition import (
    ScenarioEventCondition,
)
from ai_rpg_world.domain.world_graph.value_object.scenario_event_def import ScenarioEventDef
from ai_rpg_world.domain.world_graph.enum.interaction_effect_type import InteractionEffectTypeEnum
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
from ai_rpg_world.domain.world.enum.world_enum import SpotCategoryEnum
from ai_rpg_world.domain.world_graph.aggregate.spot_graph_aggregate import SpotGraphAggregate
from ai_rpg_world.domain.world_graph.entity.spot_node import SpotNode
from ai_rpg_world.domain.world_graph.value_object.spot_graph_id import SpotGraphId


def _build_player_status(pid: PlayerId, spawn_spot_id: SpotId) -> PlayerStatusAggregate:
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


def _make_stage(
    events: list[ScenarioEventDef],
) -> tuple[SpotGraphScenarioEventStageService, MutableWorldFlagState, InMemorySpotGraphScenarioEventProgressStore, list[str]]:
    """テスト用のstageセットアップ。最小構成のグラフ+プレイヤー。"""
    spot_id = SpotId.create(1)
    graph = SpotGraphAggregate.empty(SpotGraphId.create(1))
    graph.add_spot(SpotNode(
        spot_id=spot_id, name="Room", description="", category=SpotCategoryEnum.OTHER, parent_id=None
    ))
    data_store = InMemoryDataStore()
    spot_graph_repo = InMemorySpotGraphRepository(graph)
    spot_interior_repo = InMemorySpotInteriorRepository()
    player_status_repo = InMemoryPlayerStatusRepository(data_store)
    player_inventory_repo = InMemoryPlayerInventoryRepository(data_store)
    item_repo = InMemoryItemRepository(data_store)
    item_spec_repo = InMemoryItemSpecRepository()
    pid = PlayerId(1)
    player_status_repo.save(_build_player_status(pid, spot_id))
    player_inventory_repo.save(PlayerInventoryAggregate(player_id=pid))
    world_flags = MutableWorldFlagState()
    progress = InMemorySpotGraphScenarioEventProgressStore()
    received: list[str] = []
    stage = SpotGraphScenarioEventStageService(
        scenario_events=events,
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
    return stage, world_flags, progress, received


def _msg_effect(msg: str) -> InteractionEffect:
    return InteractionEffect(
        effect_type=InteractionEffectTypeEnum.SHOW_MESSAGE,
        parameters={"message": msg},
    )


def _flag_effect(flag: str) -> InteractionEffect:
    return InteractionEffect(
        effect_type=InteractionEffectTypeEnum.SET_FLAG,
        parameters={"flag_name": flag},
    )


class TestEventChain:
    """イベントチェーン（next_event_id + delay_ticks）のテスト"""

    def test_chain_fires_after_delay(self) -> None:
        """チェーンイベントがdelay_ticks後に発火すること"""
        events = [
            ScenarioEventDef(
                event_id="water_1",
                trigger="ON_TICK",
                once=True,
                conditions=(ScenarioEventCondition(condition_type="TICK_AT_LEAST", tick=5),),
                effects=(_msg_effect("水位1"), _flag_effect("water_1")),
                next_event_id="water_2",
                delay_ticks=3,
            ),
            ScenarioEventDef(
                event_id="water_2",
                trigger="ON_CHAIN",
                once=True,
                conditions=(),
                effects=(_msg_effect("水位2"), _flag_effect("water_2")),
            ),
        ]
        stage, flags, progress, received = _make_stage(events)

        stage.run(WorldTick(4))
        assert "water_1" not in flags.as_frozen_set()

        stage.run(WorldTick(5))
        assert "water_1" in flags.as_frozen_set()
        assert "水位1" in received
        assert "water_2" not in flags.as_frozen_set()  # まだ delay 中

        stage.run(WorldTick(7))
        assert "water_2" not in flags.as_frozen_set()  # tick 5 + 3 = 8 まで待つ

        stage.run(WorldTick(8))
        assert "water_2" in flags.as_frozen_set()
        assert "水位2" in received

    def test_three_step_chain(self) -> None:
        """3段階チェーンが順次発火すること"""
        events = [
            ScenarioEventDef(
                event_id="step1", trigger="ON_TICK", once=True,
                conditions=(ScenarioEventCondition(condition_type="TICK_AT_LEAST", tick=1),),
                effects=(_flag_effect("s1"),),
                next_event_id="step2", delay_ticks=2,
            ),
            ScenarioEventDef(
                event_id="step2", trigger="ON_CHAIN", once=True,
                conditions=(),
                effects=(_flag_effect("s2"),),
                next_event_id="step3", delay_ticks=2,
            ),
            ScenarioEventDef(
                event_id="step3", trigger="ON_CHAIN", once=True,
                conditions=(),
                effects=(_flag_effect("s3"),),
            ),
        ]
        stage, flags, _, _ = _make_stage(events)

        stage.run(WorldTick(1))
        assert "s1" in flags.as_frozen_set()

        stage.run(WorldTick(3))
        assert "s2" in flags.as_frozen_set()

        stage.run(WorldTick(5))
        assert "s3" in flags.as_frozen_set()

    def test_chain_respects_once(self) -> None:
        """チェーンイベントも once=True なら1回だけ発火すること"""
        events = [
            ScenarioEventDef(
                event_id="trigger", trigger="ON_TICK", once=True,
                conditions=(ScenarioEventCondition(condition_type="TICK_AT_LEAST", tick=1),),
                effects=(_flag_effect("triggered"),),
                next_event_id="chained", delay_ticks=1,
            ),
            ScenarioEventDef(
                event_id="chained", trigger="ON_CHAIN", once=True,
                conditions=(),
                effects=(_msg_effect("chained!"),),
            ),
        ]
        stage, _, progress, received = _make_stage(events)

        stage.run(WorldTick(1))  # trigger fires, schedules chained at tick 2
        stage.run(WorldTick(2))  # chained fires
        assert received.count("chained!") == 1

        stage.run(WorldTick(3))  # chained should NOT fire again
        assert received.count("chained!") == 1


class TestTickModulo:
    """tick_modulo 条件（周期的イベント）のテスト"""

    def test_periodic_event_fires_every_n_ticks(self) -> None:
        """tick_modulo=5 のイベントが5tick毎に発火すること"""
        events = [
            ScenarioEventDef(
                event_id="periodic",
                trigger="ON_TICK",
                once=False,
                conditions=(ScenarioEventCondition(condition_type="TICK_MODULO", tick_modulo=5),),
                effects=(_msg_effect("tick!"),),
            ),
        ]
        stage, _, _, received = _make_stage(events)

        for tick in range(1, 16):
            stage.run(WorldTick(tick))

        # tick 5, 10, 15 で発火 = 3回
        assert received.count("tick!") == 3

    def test_periodic_event_with_phase(self) -> None:
        """tick_modulo=5, tick_phase=2 でtick 2,7,12に発火すること"""
        events = [
            ScenarioEventDef(
                event_id="phased",
                trigger="ON_TICK",
                once=False,
                conditions=(ScenarioEventCondition(condition_type="TICK_MODULO", tick_modulo=5, tick_phase=2),),
                effects=(_msg_effect("phased!"),),
            ),
        ]
        stage, _, _, received = _make_stage(events)

        fired_at: list[int] = []
        for tick in range(1, 16):
            before = len(received)
            stage.run(WorldTick(tick))
            if len(received) > before:
                fired_at.append(tick)

        assert fired_at == [2, 7, 12]

    def test_periodic_event_with_zero_modulo_does_not_fire(self) -> None:
        """tick_modulo=0 のイベントは発火しないこと"""
        events = [
            ScenarioEventDef(
                event_id="bad",
                trigger="ON_TICK",
                once=False,
                conditions=(ScenarioEventCondition(condition_type="TICK_MODULO", tick_modulo=0),),
                effects=(_msg_effect("never"),),
            ),
        ]
        stage, _, _, received = _make_stage(events)
        stage.run(WorldTick(1))
        stage.run(WorldTick(5))
        assert len(received) == 0


class TestProgressStoreScheduling:
    """InMemorySpotGraphScenarioEventProgressStore のスケジュール機能テスト"""

    def test_schedule_and_due(self) -> None:
        """スケジュールしたイベントが指定tickでdueになること"""
        store = InMemorySpotGraphScenarioEventProgressStore()
        store.schedule("ev1", fire_at_tick=10)
        assert store.due_event_ids(9) == []
        assert store.due_event_ids(10) == ["ev1"]
        assert store.due_event_ids(15) == ["ev1"]

    def test_unschedule(self) -> None:
        """unscheduleでイベントが除去されること"""
        store = InMemorySpotGraphScenarioEventProgressStore()
        store.schedule("ev1", fire_at_tick=10)
        store.unschedule("ev1")
        assert store.due_event_ids(10) == []

    def test_multiple_schedules(self) -> None:
        """複数イベントが独立にスケジュールされること"""
        store = InMemorySpotGraphScenarioEventProgressStore()
        store.schedule("ev1", fire_at_tick=5)
        store.schedule("ev2", fire_at_tick=10)
        assert set(store.due_event_ids(10)) == {"ev1", "ev2"}
        assert store.due_event_ids(7) == ["ev1"]
