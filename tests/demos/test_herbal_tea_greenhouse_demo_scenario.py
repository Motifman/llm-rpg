"""Phase 2 機能の総合デモ end-to-end 検証。

`data/scenarios/herbal_tea_greenhouse_demo.json` を読み込み、
1 つのシナリオで以下の Phase 2 primitive をすべて活用していることを保証する:

- #104 数量セマンティクス
  - GIVE_ITEM(quantity=3) / REMOVE_ITEM(quantity=3)
  - HAS_ITEM(required_quantity=3 / required_quantity=1)
- #105 非対称 reactive binding
  - on_false_state_updates が空 tuple → 「条件不成立時は触らない」
  - 1 フィールド (`phase`) で 3 段階機 (idle / brewing / ready) を表現
- #106 合成糖衣 `all_of`
  - tea_brewer の predicate を `all_of` でフラットに記述
- #107 null sentinel
  - herb_planter の `last_harvest_tick: null` で「まだ起きていない」を
    マジックナンバー無しで表現
  - `treat_missing_as_passed: true` で「初期は ripe」を担保

これらが組み合わさって「3 枚採取 → 抽出器に 3+1 投入 → 4 tick 待ち →
茶 1 個入手」の往復サイクルが成立することを E2E で保証する。
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
    count_owned_item_instances_by_spec,
    grant_item_specs_to_inventory,
)
from ai_rpg_world.application.world_graph.world_flag_state import MutableWorldFlagState
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.domain.item.enum.item_enum import ItemType, Rarity
from ai_rpg_world.domain.item.read_model.item_spec_read_model import ItemSpecReadModel
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.item.value_object.max_stack_size import MaxStackSize
from ai_rpg_world.domain.player.aggregate.player_inventory_aggregate import (
    PlayerInventoryAggregate,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
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
    / "herbal_tea_greenhouse_demo.json"
)


@pytest.fixture
def greenhouse():
    """温室シナリオを load し、interaction app + reactive binding stage を返す。"""
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
    for spawn in loaded.player_spawns:
        pid = PlayerId(spawn.player_id)
        inventory_repo.save(PlayerInventoryAggregate(player_id=pid))
        if spawn.initial_item_spec_ids:
            grant_item_specs_to_inventory(
                pid, spawn.initial_item_spec_ids,
                item_repo, item_spec_repo, inventory_repo,
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
    return SpotId.create(loaded.id_mapper.get_int("spot", "greenhouse"))


def _planter_id(loaded) -> SpotObjectId:
    return SpotObjectId.create(loaded.id_mapper.get_int("object", "herb_planter"))


def _brewer_id(loaded) -> SpotObjectId:
    return SpotObjectId.create(loaded.id_mapper.get_int("object", "tea_brewer"))


def _player_id(loaded) -> PlayerId:
    return PlayerId(loaded.player_spawns[0].player_id)


def _planter_state(interior_repo, loaded) -> dict:
    interior = interior_repo.find_by_spot_id(_spot_id(loaded))
    return next(o for o in interior.objects if o.object_id == _planter_id(loaded)).state


def _brewer_state(interior_repo, loaded) -> dict:
    interior = interior_repo.find_by_spot_id(_spot_id(loaded))
    return next(o for o in interior.objects if o.object_id == _brewer_id(loaded)).state


def _spec_counts(inventory_repo, item_repo, loaded) -> dict[str, int]:
    """{string_id -> 所持個数} を返す。"""
    inv = inventory_repo.find_by_id(_player_id(loaded))
    counts = count_owned_item_instances_by_spec(inv, item_repo)
    spec_int_to_str = {
        loaded.id_mapper.get_int("item_spec", s): s
        for s in ("herb_leaf", "coal", "tea_cup")
    }
    return {spec_int_to_str[k.value]: v for k, v in counts.items()}


class TestHerbalTeaGreenhouseDemo:
    """herbal_tea_greenhouse_demo.json で Phase 2 機能群が組み合わさることの保証。"""

    def test_initial_state_uses_null_sentinel_and_treat_as_passed(self, greenhouse) -> None:
        """初期: planter は available=true / last_harvest_tick=null、binding 1 周後も維持される。

        Phase 2-B (#107) の null sentinel + `treat_missing_as_passed=true` により、
        マジックナンバー無しで「初期から摘める」を表現できることを保証。
        """
        loaded, interior_repo, inv_repo, item_repo, _, binding_stage = greenhouse
        s = _planter_state(interior_repo, loaded)
        assert s["available"] is True
        assert s["last_harvest_tick"] is None  # JSON で null
        # 1 周 binding を回しても available=true のまま (predicate True → on_true は冪等)
        binding_stage.run(WorldTick(1))
        assert _planter_state(interior_repo, loaded)["available"] is True
        # 持ち物: 炭 2、薬草 0、茶 0
        assert _spec_counts(inv_repo, item_repo, loaded) == {"coal": 2}

    def test_harvest_grants_three_leaves_via_quantity_effect(self, greenhouse) -> None:
        """harvest で薬草が 3 枚一括入手される (Phase 2-A #104 GIVE_ITEM quantity=3)。"""
        loaded, interior_repo, inv_repo, item_repo, app, _ = greenhouse
        app.execute_interaction(
            _player_id(loaded), _planter_id(loaded), "harvest",
            current_tick=WorldTick(2),
        )
        counts = _spec_counts(inv_repo, item_repo, loaded)
        assert counts["herb_leaf"] == 3
        # planter は枯れ + last_harvest_tick=2
        s = _planter_state(interior_repo, loaded)
        assert s["available"] is False
        assert s["last_harvest_tick"] == 2

    def test_harvest_blocked_until_regrowth_then_succeeds(self, greenhouse) -> None:
        """採取後 ticks_offset (=6) tick の間は再採取できず、経過後に再 ripe。

        非対称 binding (Phase 2-B #105): on_false が空 tuple なので、
        predicate False の間 planter.available は触られず False のまま維持される。
        on_true のみ available=true を書き戻す。
        """
        loaded, interior_repo, _, _, app, binding_stage = greenhouse
        app.execute_interaction(
            _player_id(loaded), _planter_id(loaded), "harvest",
            current_tick=WorldTick(2),
        )
        # tick 3-7: 経過 1-5 < 6、predicate False、binding は asymmetric なので触らない
        for t in range(3, 8):
            binding_stage.run(WorldTick(t))
            assert _planter_state(interior_repo, loaded)["available"] is False, (
                f"tick={t} で早期再生"
            )
            # 早期再採取は弾かれる
            with pytest.raises(InteractionNotAllowedException):
                app.execute_interaction(
                    _player_id(loaded), _planter_id(loaded), "harvest",
                    current_tick=WorldTick(t),
                )
        # tick 8: 2+6=8、predicate True → available=true (on_true)
        binding_stage.run(WorldTick(8))
        assert _planter_state(interior_repo, loaded)["available"] is True
        # 再採取成功
        app.execute_interaction(
            _player_id(loaded), _planter_id(loaded), "harvest",
            current_tick=WorldTick(9),
        )

    def test_infuse_requires_quantity_three_leaves_and_one_coal(self, greenhouse) -> None:
        """抽出には薬草 3 + 炭 1 が必要 (Phase 2-A #104 HAS_ITEM required_quantity)。"""
        loaded, _, inv_repo, item_repo, app, _ = greenhouse
        # 薬草 3 枚を確保
        app.execute_interaction(
            _player_id(loaded), _planter_id(loaded), "harvest",
            current_tick=WorldTick(1),
        )
        # 投入成功
        app.execute_interaction(
            _player_id(loaded), _brewer_id(loaded), "infuse",
            current_tick=WorldTick(2),
        )
        # 投入後: 薬草 0、炭 1 (2-1)、茶 0
        counts = _spec_counts(inv_repo, item_repo, loaded)
        assert counts.get("herb_leaf", 0) == 0
        assert counts["coal"] == 1
        assert counts.get("tea_cup", 0) == 0

    def test_infuse_blocked_when_leaves_insufficient(self, greenhouse) -> None:
        """薬草が 2 枚以下なら required_quantity=3 で拒否される。"""
        loaded, _, inv_repo, item_repo, app, _ = greenhouse
        # 採取せず (薬草 0) で投入を試みる
        with pytest.raises(InteractionNotAllowedException):
            app.execute_interaction(
                _player_id(loaded), _brewer_id(loaded), "infuse",
                current_tick=WorldTick(1),
            )
        # 失敗時は炭も消費されない
        assert _spec_counts(inv_repo, item_repo, loaded) == {"coal": 2}

    def test_brewer_uses_all_of_predicate_with_phase_lifecycle(self, greenhouse) -> None:
        """抽出開始 4 tick 後に reactive binding (`all_of` 糖衣) が phase を ready に推移させる。

        Phase 2-B 非対称 binding により phase は `infuse` interaction が
        idle→brewing、binding が brewing→ready、`collect_tea` interaction が
        ready→idle と各フェーズを 1 主体ずつ書き換える。1 フィールドで
        3 段階機を回せる構造の確認。
        """
        loaded, interior_repo, _, _, app, binding_stage = greenhouse
        app.execute_interaction(
            _player_id(loaded), _planter_id(loaded), "harvest",
            current_tick=WorldTick(1),
        )
        app.execute_interaction(
            _player_id(loaded), _brewer_id(loaded), "infuse",
            current_tick=WorldTick(2),
        )
        # phase=brewing、started_at_tick=2
        assert _brewer_state(interior_repo, loaded)["phase"] == "brewing"
        # tick 3-5: 経過 1-3 < 4、phase は brewing のまま
        for t in range(3, 6):
            binding_stage.run(WorldTick(t))
            assert _brewer_state(interior_repo, loaded)["phase"] == "brewing"
        # tick 6: 2+4=6、all_of の両条件が成立 → phase=ready
        binding_stage.run(WorldTick(6))
        assert _brewer_state(interior_repo, loaded)["phase"] == "ready"

    def test_collect_tea_yields_one_cup_and_resets_brewer(self, greenhouse) -> None:
        """collect で茶 1 杯を入手し、brewer は phase=idle に 1 行リセット。

        Phase 2-B により reset effect は `phase=idle` の 1 フィールドだけで
        済む (旧 same-key-set 制約下では started_at_tick も併せて reset
        する必要があった)。
        """
        loaded, interior_repo, inv_repo, item_repo, app, binding_stage = greenhouse
        app.execute_interaction(
            _player_id(loaded), _planter_id(loaded), "harvest", current_tick=WorldTick(1),
        )
        app.execute_interaction(
            _player_id(loaded), _brewer_id(loaded), "infuse", current_tick=WorldTick(2),
        )
        for t in range(3, 7):
            binding_stage.run(WorldTick(t))
        assert _brewer_state(interior_repo, loaded)["phase"] == "ready"

        app.execute_interaction(
            _player_id(loaded), _brewer_id(loaded), "collect_tea",
            current_tick=WorldTick(7),
        )
        # 茶 1、薬草 0、炭 1
        counts = _spec_counts(inv_repo, item_repo, loaded)
        assert counts["tea_cup"] == 1
        assert counts.get("herb_leaf", 0) == 0
        assert counts["coal"] == 1
        # brewer は idle に戻る (1 フィールドリセット)
        assert _brewer_state(interior_repo, loaded)["phase"] == "idle"

    def test_full_two_cycles_with_regrowth(self, greenhouse) -> None:
        """2 周回す: 採取→抽出→4 tick→収穫、待機→再採取→抽出→4 tick→収穫。

        以下の primitive がすべて回ることを 1 通しで確認:
        - quantity (GIVE 3 / REMOVE 3, 1 / HAS required 3, 1)
        - 非対称 binding (両 object とも on_false=())
        - all_of 糖衣
        - null sentinel + treat_missing_as_passed (初期 ripe)
        - RECORD_OBJECT_STATE_TICK + OBJECT_STATE_TICK_AT_LEAST
        """
        loaded, interior_repo, inv_repo, item_repo, app, binding_stage = greenhouse

        # ---- 1 周目 ----
        app.execute_interaction(
            _player_id(loaded), _planter_id(loaded), "harvest", current_tick=WorldTick(1),
        )
        app.execute_interaction(
            _player_id(loaded), _brewer_id(loaded), "infuse", current_tick=WorldTick(2),
        )
        for t in range(3, 7):
            binding_stage.run(WorldTick(t))
        app.execute_interaction(
            _player_id(loaded), _brewer_id(loaded), "collect_tea", current_tick=WorldTick(7),
        )
        assert _spec_counts(inv_repo, item_repo, loaded)["tea_cup"] == 1

        # ---- 再生待ち (採取 tick=1、6 tick 経過で再 ripe = tick 7 以降) ----
        for t in range(7, 8):
            binding_stage.run(WorldTick(t))
        assert _planter_state(interior_repo, loaded)["available"] is True

        # ---- 2 周目 ----
        app.execute_interaction(
            _player_id(loaded), _planter_id(loaded), "harvest", current_tick=WorldTick(8),
        )
        app.execute_interaction(
            _player_id(loaded), _brewer_id(loaded), "infuse", current_tick=WorldTick(9),
        )
        for t in range(10, 14):
            binding_stage.run(WorldTick(t))
        app.execute_interaction(
            _player_id(loaded), _brewer_id(loaded), "collect_tea", current_tick=WorldTick(14),
        )
        # 茶 2 杯、炭 0、薬草 0
        counts = _spec_counts(inv_repo, item_repo, loaded)
        assert counts["tea_cup"] == 2
        assert counts.get("coal", 0) == 0
        assert counts.get("herb_leaf", 0) == 0
