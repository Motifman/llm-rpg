"""環境系 #10 (経時劣化) の最小デモシナリオの end-to-end 検証。

`data/scenarios/decay_demo.json` を読み込み、ReactiveObjectStateBinding
が OBJECT_STATE_TICK_AT_LEAST predicate で last_cleaned_tick からの
経過を見て rust_level を clean → rusty に劣化させ、interaction "clean"
が timestamp を更新することで rust_level がリセットされる流れを保証する。

新 primitive は導入していない。PR #98 (reactive 基盤) と PR #100
(RECORD_OBJECT_STATE_TICK effect) を組み合わせるだけで経時劣化が
実装できることを示すデモ。
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
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.service.spot_interaction_service import (
    SpotInteractionService,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from ai_rpg_world.infrastructure.repository.in_memory_data_store import InMemoryDataStore
from ai_rpg_world.infrastructure.repository.in_memory_item_repository import (
    InMemoryItemRepository,
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
    / "decay_demo.json"
)


@pytest.fixture
def decay():
    """シナリオを読み込んで stage / repos / interaction service を返す。"""
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
    binding_stage = ReactiveObjectStateBindingStageService(
        bindings=loaded.reactive_object_state_bindings,
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=interior_repo,
        condition_evaluator=evaluator,
    )
    interaction_svc = SpotInteractionService()
    return loaded, interior_repo, binding_stage, interaction_svc


def _spot_id(loaded) -> SpotId:
    return SpotId.create(loaded.id_mapper.get_int("spot", "armory"))


def _sword_id(loaded) -> SpotObjectId:
    return SpotObjectId.create(loaded.id_mapper.get_int("object", "iron_sword"))


def _sword_state(interior_repo, loaded) -> dict:
    interior = interior_repo.find_by_spot_id(_spot_id(loaded))
    obj = next(o for o in interior.objects if o.object_id == _sword_id(loaded))
    return obj.state


def _clean_sword(interaction_svc, interior_repo, loaded, *, current_tick: int) -> None:
    interior = interior_repo.find_by_spot_id(_spot_id(loaded))
    result = interaction_svc.execute_interaction(
        interior,
        _sword_id(loaded),
        "clean",
        frozenset(),
        frozenset(),
        current_tick=WorldTick(current_tick),
    )
    interior_repo.save(_spot_id(loaded), result.new_interior)


class TestDecayDemoScenario:
    """decay_demo.json が #10 経時劣化の仕様通りに動く。"""

    def test_initial_state_is_clean(self, decay) -> None:
        """初期状態は rust_level=clean、last_cleaned_tick=0。"""
        loaded, interior_repo, _, _ = decay
        s = _sword_state(interior_repo, loaded)
        assert s["rust_level"] == "clean"
        assert s["last_cleaned_tick"] == 0

    def test_sword_rusts_after_offset_ticks_without_cleaning(self, decay) -> None:
        """手入れせず ticks_offset (=10) tick 経過すると rust_level=rusty に劣化。"""
        loaded, interior_repo, binding_stage, _ = decay
        # tick 1-9: まだ rusty にならない（経過 1-9 < 10）
        for t in range(1, 10):
            binding_stage.run(WorldTick(t))
            assert _sword_state(interior_repo, loaded)["rust_level"] == "clean", (
                f"tick={t} で早期に錆びた"
            )
        # tick 10: 0+10=10、predicate true → rusty
        binding_stage.run(WorldTick(10))
        assert _sword_state(interior_repo, loaded)["rust_level"] == "rusty"

    def test_cleaning_resets_rust_at_next_tick(self, decay) -> None:
        """手入れ interaction で last_cleaned_tick が更新され、次 tick で rust_level=clean に戻る。"""
        loaded, interior_repo, binding_stage, interaction_svc = decay
        # 劣化させる
        for t in range(1, 11):
            binding_stage.run(WorldTick(t))
        assert _sword_state(interior_repo, loaded)["rust_level"] == "rusty"

        # tick 11 で手入れ
        _clean_sword(interaction_svc, interior_repo, loaded, current_tick=11)
        assert _sword_state(interior_repo, loaded)["last_cleaned_tick"] == 11

        # 次 tick の binding で rust_level=clean に復帰（11+10=21、tick 12 < 21 → on_false）
        binding_stage.run(WorldTick(12))
        s = _sword_state(interior_repo, loaded)
        assert s["rust_level"] == "clean"
        assert s["last_cleaned_tick"] == 11

    def test_cleaning_extends_clean_window(self, decay) -> None:
        """手入れすると次回劣化までの猶予が ticks_offset 分延長される。"""
        loaded, interior_repo, binding_stage, interaction_svc = decay
        # tick 5 で手入れ → last_cleaned_tick=5
        _clean_sword(interaction_svc, interior_repo, loaded, current_tick=5)

        # tick 6-14: 経過 1-9 < 10 なので clean のまま
        for t in range(6, 15):
            binding_stage.run(WorldTick(t))
            assert _sword_state(interior_repo, loaded)["rust_level"] == "clean", (
                f"tick={t} で早期に錆びた"
            )
        # tick 15: 5+10=15 で predicate true → rusty
        binding_stage.run(WorldTick(15))
        assert _sword_state(interior_repo, loaded)["rust_level"] == "rusty"
