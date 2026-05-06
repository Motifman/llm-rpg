"""アイテム × 環境クラフトの最小デモ end-to-end 検証。

`data/scenarios/cauldron_crafting_demo.json` を読み込み、

1. 鉄鉱石を炉にくべる (stoke) と REMOVE_ITEM + RECORD_OBJECT_STATE_TICK +
   CHANGE_OBJECT_STATE が連動して進行が始まる
2. ReactiveObjectStateBinding が AND(OBJECT_STATE, OBJECT_STATE_TICK_AT_LEAST)
   predicate で 5 tick 経過後に ready=true に切り替える
3. インゴットを取り出す (collect) と GIVE_ITEM + 状態リセットで炉が
   再利用可能になる

の一連の流れを保証する。新 primitive ゼロ — Phase 1 として既存基盤の
組み合わせだけでクラフトが書けることを実証するデモ。
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
from ai_rpg_world.application.world_graph.spot_interaction_application_service import (
    SpotInteractionApplicationService,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    grant_item_specs_to_inventory,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.read_model.item_spec_read_model import ItemSpecReadModel
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
)
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
    / "cauldron_crafting_demo.json"
)


@pytest.fixture
def cauldron():
    """炉 / プレイヤー / 鉄鉱石 2 個を初期化したコンテキストを返す。"""
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

    # シナリオ JSON で定義された item_spec を read model としてリポジトリへ登録
    for item_def in loaded.item_spec_definitions:
        item_spec_repo.save(
            ItemSpecReadModel(
                item_spec_id=item_def.spec_id,
                name=item_def.name,
                item_type=ItemType.MATERIAL,
                rarity=Rarity.COMMON,
                description=item_def.description,
                max_stack_size=MaxStackSize(99),
            )
        )

    flags = MutableWorldFlagState()

    # プレイヤーごとに inventory を作成し、initial_items を実体化
    for spawn in loaded.player_spawns:
        pid = PlayerId(spawn.player_id)
        inventory_repo.save(PlayerInventoryAggregate(player_id=pid))
        if spawn.initial_item_spec_ids:
            grant_item_specs_to_inventory(
                pid,
                spawn.initial_item_spec_ids,
                item_repo,
                item_spec_repo,
                inventory_repo,
            )

    interaction_app = SpotInteractionApplicationService(
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=interior_repo,
        player_inventory_repository=inventory_repo,
        item_repository=item_repo,
        item_spec_repository=item_spec_repo,
        world_flag_state=flags,
        player_status_repository=status_repo,
    )
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
    return loaded, interior_repo, inventory_repo, item_repo, interaction_app, binding_stage


def _spot_id(loaded) -> SpotId:
    return SpotId.create(loaded.id_mapper.get_int("spot", "smithy"))


def _furnace_id(loaded) -> SpotObjectId:
    return SpotObjectId.create(loaded.id_mapper.get_int("object", "smelting_furnace"))


def _player_id(loaded) -> PlayerId:
    return PlayerId(loaded.player_spawns[0].player_id)


def _furnace_state(interior_repo, loaded) -> dict:
    interior = interior_repo.find_by_spot_id(_spot_id(loaded))
    obj = next(o for o in interior.objects if o.object_id == _furnace_id(loaded))
    return obj.state


def _owned_spec_strs(inventory_repo, item_repo, loaded) -> list[str]:
    """所持アイテム instance を string id 一覧で返す（重複保持）。"""
    spec_int_to_str = {
        loaded.id_mapper.get_int("item_spec", s): s
        for s in ("iron_ore", "iron_ingot")
    }
    inv = inventory_repo.find_by_id(_player_id(loaded))
    owned: list[str] = []
    for i in range(inv.max_slots):
        iid = inv.get_item_instance_id_by_slot(SlotId(i))
        if iid is None:
            continue
        agg = item_repo.find_by_id(iid)
        if agg is None:
            continue
        owned.append(spec_int_to_str[agg.item_spec.item_spec_id.value])
    return sorted(owned)


class TestCauldronCraftingDemoScenario:
    """cauldron_crafting_demo.json が item × environment の双方向作用を保証する。"""

    def test_initial_state_has_two_ores_and_idle_furnace(self, cauldron) -> None:
        """初期状態で炉は smelting=false / ready=false、プレイヤーは鉄鉱石 2 個所持。"""
        loaded, interior_repo, inventory_repo, item_repo, _, _ = cauldron
        s = _furnace_state(interior_repo, loaded)
        assert s["smelting"] is False
        assert s["ready"] is False
        assert _owned_spec_strs(inventory_repo, item_repo, loaded) == ["iron_ore", "iron_ore"]

    def test_stoke_consumes_ore_and_starts_smelting(self, cauldron) -> None:
        """stoke で iron_ore が 1 個消費され、炉が smelting=true / started_at_tick 記録になる。"""
        loaded, interior_repo, inventory_repo, item_repo, app, _ = cauldron
        app.execute_interaction(
            _player_id(loaded),
            _furnace_id(loaded),
            "stoke",
            current_tick=WorldTick(2),
        )
        s = _furnace_state(interior_repo, loaded)
        assert s["smelting"] is True
        assert s["started_at_tick"] == 2
        assert s["ready"] is False
        assert _owned_spec_strs(inventory_repo, item_repo, loaded) == ["iron_ore"]

    def test_stoke_blocked_while_already_smelting(self, cauldron) -> None:
        """製錬中の炉に再度 stoke しようとすると OBJECT_STATE precondition に弾かれる。"""
        loaded, _, _, _, app, _ = cauldron
        app.execute_interaction(
            _player_id(loaded), _furnace_id(loaded), "stoke", current_tick=WorldTick(2),
        )
        with pytest.raises(InteractionNotAllowedException):
            app.execute_interaction(
                _player_id(loaded), _furnace_id(loaded), "stoke", current_tick=WorldTick(3),
            )

    def test_collect_blocked_until_ready(self, cauldron) -> None:
        """製錬完了前に collect しようとすると InteractionNotAllowedException で拒否される。"""
        loaded, _, _, _, app, binding_stage = cauldron
        app.execute_interaction(
            _player_id(loaded), _furnace_id(loaded), "stoke", current_tick=WorldTick(2),
        )
        binding_stage.run(WorldTick(3))  # まだ ready=false
        with pytest.raises(InteractionNotAllowedException):
            app.execute_interaction(
                _player_id(loaded), _furnace_id(loaded), "collect",
                current_tick=WorldTick(4),
            )

    def test_furnace_becomes_ready_after_offset(self, cauldron) -> None:
        """stoke から ticks_offset (=5) tick 経過すると reactive binding が ready=true に切り替える。"""
        loaded, interior_repo, _, _, app, binding_stage = cauldron
        app.execute_interaction(
            _player_id(loaded), _furnace_id(loaded), "stoke", current_tick=WorldTick(2),
        )
        # tick 3-6: まだ ready=false
        for t in range(3, 7):
            binding_stage.run(WorldTick(t))
            assert _furnace_state(interior_repo, loaded)["ready"] is False, f"tick={t} で早期完成"
        # tick 7: started_at=2, 2+5=7, predicate true → ready=true
        binding_stage.run(WorldTick(7))
        assert _furnace_state(interior_repo, loaded)["ready"] is True

    def test_full_cycle_yields_ingot_and_resets_furnace(self, cauldron) -> None:
        """stoke → 経過 → collect でインゴット入手し、炉は再利用可能な状態に戻る。"""
        loaded, interior_repo, inventory_repo, item_repo, app, binding_stage = cauldron
        app.execute_interaction(
            _player_id(loaded), _furnace_id(loaded), "stoke", current_tick=WorldTick(2),
        )
        for t in range(3, 8):
            binding_stage.run(WorldTick(t))
        assert _furnace_state(interior_repo, loaded)["ready"] is True

        app.execute_interaction(
            _player_id(loaded), _furnace_id(loaded), "collect", current_tick=WorldTick(8),
        )
        # インゴット入手、鉱石 1 個残
        assert sorted(_owned_spec_strs(inventory_repo, item_repo, loaded)) == [
            "iron_ingot", "iron_ore",
        ]
        # 炉はリセット
        s = _furnace_state(interior_repo, loaded)
        assert s["smelting"] is False
        assert s["ready"] is False

        # 次 tick で binding が念のため再評価しても ready=false のまま（smelting=false なので）
        binding_stage.run(WorldTick(9))
        assert _furnace_state(interior_repo, loaded)["ready"] is False

    def test_second_cycle_reuses_furnace(self, cauldron) -> None:
        """2 周目: 残った鉱石でもう一度 stoke → ready → collect が回せる。"""
        loaded, interior_repo, inventory_repo, item_repo, app, binding_stage = cauldron
        # 1 周目
        app.execute_interaction(
            _player_id(loaded), _furnace_id(loaded), "stoke", current_tick=WorldTick(2),
        )
        for t in range(3, 8):
            binding_stage.run(WorldTick(t))
        app.execute_interaction(
            _player_id(loaded), _furnace_id(loaded), "collect", current_tick=WorldTick(8),
        )
        # 2 周目
        app.execute_interaction(
            _player_id(loaded), _furnace_id(loaded), "stoke", current_tick=WorldTick(10),
        )
        for t in range(11, 16):
            binding_stage.run(WorldTick(t))
        assert _furnace_state(interior_repo, loaded)["ready"] is True
        app.execute_interaction(
            _player_id(loaded), _furnace_id(loaded), "collect", current_tick=WorldTick(16),
        )
        # インゴット 2 個 / 鉱石 0 個
        assert sorted(_owned_spec_strs(inventory_repo, item_repo, loaded)) == [
            "iron_ingot", "iron_ingot",
        ]
