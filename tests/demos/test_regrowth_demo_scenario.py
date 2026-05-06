"""環境系 #12 (資源回復) の最小デモシナリオの end-to-end 検証。

`data/scenarios/regrowth_demo.json` を読み込み、scenario_event の
RECORD_OBJECT_STATE_TICK effect が last_harvest_tick を書き込み、
ReactiveObjectStateBindingStageService が
OBJECT_STATE_TICK_AT_LEAST predicate でその経過を見て
available を再生（再 true 化）するまでの一連の流れを保証する。

新 primitive は RECORD_OBJECT_STATE_TICK の 1 種のみ。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_graph.reactive_object_state_binding_stage_service import (
    ReactiveObjectStateBindingStageService,
)
from ai_rpg_world.application.world_graph.scenario_condition_evaluator import (
    ScenarioConditionEvaluator,
)
from ai_rpg_world.application.world_graph.spot_graph_scenario_event_stage_service import (
    SpotGraphScenarioEventStageService,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import (
    InMemoryItemRepository,
)
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


SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "regrowth_demo.json"
)


@pytest.fixture
def regrowth():
    """シナリオを読み込んで scenario_event_stage / reactive_object_state_stage / repos を返す。"""
    loaded = ScenarioLoader().load_from_file(SCENARIO_PATH)
    graph = loaded.graph
    for spawn in loaded.player_spawns:
        graph.place_entity(EntityId.create(spawn.player_id), spawn.spawn_spot_id)
    graph.clear_events()

    spot_graph_repo = InMemorySpotGraphRepository(graph)
    interior_repo = InMemorySpotInteriorRepository()
    for sid, interior in loaded.interiors.items():
        interior_repo.save(sid, interior)
    data_store = InMemoryDataStore()
    status_repo = InMemoryPlayerStatusRepository(data_store)
    inventory_repo = InMemoryPlayerInventoryRepository(data_store)
    item_repo = InMemoryItemRepository(data_store)
    item_spec_repo = InMemoryItemSpecRepository()
    for spawn in loaded.player_spawns:
        inventory_repo.save(PlayerInventoryAggregate(player_id=PlayerId(spawn.player_id)))

    flags = MutableWorldFlagState()
    evaluator = ScenarioConditionEvaluator(
        world_flag_state=flags,
        spot_interior_repository=interior_repo,
        player_status_repository=status_repo,
        player_inventory_repository=inventory_repo,
        item_repository=item_repo,
    )
    event_stage = SpotGraphScenarioEventStageService(
        scenario_events=loaded.scenario_events,
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=interior_repo,
        player_status_repository=status_repo,
        player_inventory_repository=inventory_repo,
        item_repository=item_repo,
        item_spec_repository=item_spec_repo,
        world_flag_state=flags,
        condition_evaluator=evaluator,
    )
    binding_stage = ReactiveObjectStateBindingStageService(
        bindings=loaded.reactive_object_state_bindings,
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=interior_repo,
        condition_evaluator=evaluator,
    )
    return loaded, interior_repo, event_stage, binding_stage


def _bush_state(interior_repo, loaded) -> dict:
    spot_int = loaded.id_mapper.get_int("spot", "forest_clearing")
    interior = interior_repo.find_by_spot_id(SpotId.create(spot_int))
    obj_int = loaded.id_mapper.get_int("object", "berry_bush")
    obj = next(o for o in interior.objects if o.object_id == SpotObjectId.create(obj_int))
    return obj.state


def _run_tick(event_stage, binding_stage, tick: int) -> None:
    event_stage.run(WorldTick(tick))
    binding_stage.run(WorldTick(tick))


class TestRegrowthDemoScenario:
    """regrowth_demo.json が #12 資源回復の仕様通りに動く。"""

    def test_initial_state_is_available(self, regrowth) -> None:
        """初期状態は available=true、last_harvest_tick=-100（十分に過去）。"""
        loaded, interior_repo, _, _ = regrowth
        s = _bush_state(interior_repo, loaded)
        assert s["available"] is True
        assert s["last_harvest_tick"] == -100

    def test_wildlife_event_records_tick_and_depletes(self, regrowth) -> None:
        """tick 5 で scenario_event が発火し last_harvest_tick=5、available=false になる。"""
        loaded, interior_repo, event_stage, binding_stage = regrowth
        # tick 1-4: 何も起きない
        for t in range(1, 5):
            _run_tick(event_stage, binding_stage, t)
        s = _bush_state(interior_repo, loaded)
        assert s["available"] is True
        # tick 5: scenario_event 発火
        _run_tick(event_stage, binding_stage, 5)
        s = _bush_state(interior_repo, loaded)
        assert s["available"] is False
        assert s["last_harvest_tick"] == 5

    def test_bush_regrows_after_offset_ticks(self, regrowth) -> None:
        """採取から ticks_offset (=10) tick 経過すると available が true に再生。"""
        loaded, interior_repo, event_stage, binding_stage = regrowth
        # tick 5 で採取
        for t in range(1, 6):
            _run_tick(event_stage, binding_stage, t)
        assert _bush_state(interior_repo, loaded)["available"] is False

        # tick 6-14 はまだ false (経過 1-9 tick < 10)
        for t in range(6, 15):
            _run_tick(event_stage, binding_stage, t)
            assert _bush_state(interior_repo, loaded)["available"] is False, f"tick={t} で再生してしまった"

        # tick 15: 5+10=15、predicate true → available 再生
        _run_tick(event_stage, binding_stage, 15)
        s = _bush_state(interior_repo, loaded)
        assert s["available"] is True
        # last_harvest_tick は再採取まで残る
        assert s["last_harvest_tick"] == 5

    def test_event_does_not_refire_after_once(self, regrowth) -> None:
        """once=true の scenario_event は一度しか発火しないので、再生後に再採取はされない。"""
        loaded, interior_repo, event_stage, binding_stage = regrowth
        for t in range(1, 16):
            _run_tick(event_stage, binding_stage, t)
        # tick 15 時点で再生済み
        assert _bush_state(interior_repo, loaded)["available"] is True

        # tick 16-30: scenario_event は once=true なので二度目は起きない → available のまま
        for t in range(16, 31):
            _run_tick(event_stage, binding_stage, t)
            s = _bush_state(interior_repo, loaded)
            assert s["available"] is True, f"tick={t} で再採取されてしまった"
            assert s["last_harvest_tick"] == 5
