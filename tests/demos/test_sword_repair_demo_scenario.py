"""Phase 4-B 全体の end-to-end 検証 (二者間の相互作用デモ)。

`data/scenarios/sword_repair_demo.json` を読み込み:

- 修理キット (使う側) と 錆びた剣 (使われる側) を持って作業台に立つ
- repair_with_kit インタラクション:
  - precondition: 修理キット.used=false かつ 剣.rust=high
  - effect: 修理キット → used=true、剣 → rust=low + last_repaired_tick 記録
- 一度使った修理キットは used=true なので 2 度目は precondition で拒否される
- 別 instance の修理キットなら別の錆びた剣を直せる (per-instance 独立性)

これにより以下が end-to-end で動くことを保証する:
- Phase 4-A の使う側 effect / precondition (`CHANGE_ITEM_INSTANCE_STATE`,
  `ITEM_INSTANCE_STATE`)
- Phase 4-B の使われる側 effect / precondition
  (`CHANGE_TARGET_ITEM_INSTANCE_STATE`,
   `RECORD_TARGET_ITEM_INSTANCE_STATE_TICK`, `TARGET_ITEM_INSTANCE_STATE`)
- アプリ層の `target_item_instance_id` 配線 + 同 ID 重複ガード
- 使う側 / 使われる側両方の永続化 (`item_repository.save` を別々に呼ぶ)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.common.exceptions import ApplicationException
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
from ai_rpg_world.domain.item.value_object.item_instance_id import ItemInstanceId
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
    / "sword_repair_demo.json"
)


@pytest.fixture
def smithy():
    """鍛冶場シナリオを load して app + repos を返す。"""
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
    return loaded, interior_repo, inventory_repo, item_repo, interaction_app


def _spot_id(loaded) -> SpotId:
    return SpotId.create(loaded.id_mapper.get_int("spot", "smithy"))


def _player_id(loaded) -> PlayerId:
    return PlayerId(loaded.player_spawns[0].player_id)


def _bench_id(loaded) -> SpotObjectId:
    return SpotObjectId.create(loaded.id_mapper.get_int("object", "repair_bench"))


def _instances_of(inventory_repo, item_repo, loaded, spec_string_id: str) -> list[ItemInstanceId]:
    """指定 spec のインスタンス ID を slot 順に返す。"""
    inv = inventory_repo.find_by_id(_player_id(loaded))
    spec_int = loaded.id_mapper.get_int("item_spec", spec_string_id)
    out = []
    for i in range(inv.max_slots):
        iid = inv.get_item_instance_id_by_slot(SlotId(i))
        if iid is None:
            continue
        agg = item_repo.find_by_id(iid)
        if agg is not None and agg.item_spec.item_spec_id.value == spec_int:
            out.append(iid)
    return out


def _set_item_state(item_repo, instance_id: ItemInstanceId, state: dict) -> None:
    """テスト用ヘルパ: 指定 instance に initial state を仕込んで永続化する。

    scenario_loader 側で initial_state を仕込む経路はまだ無いので、テスト
    内で明示的に aggregate を初期化するのを 1 行で書けるようにする。
    """
    agg = item_repo.find_by_id(instance_id)
    agg.merge_state(state)
    item_repo.save(agg)


class TestSwordRepairDemo:
    """Phase 4-B 全体: 物Aを物Bに使うインタラクションが end-to-end で動く。"""

    def test_repair_changes_both_kit_and_sword_state(self, smithy) -> None:
        """修理を実行すると 修理キット → used=true、剣 → rust=low + last_repaired_tick が永続化される。"""
        loaded, _, inv_repo, item_repo, app = smithy
        kit = _instances_of(inv_repo, item_repo, loaded, "repair_kit")[0]
        sword = _instances_of(inv_repo, item_repo, loaded, "rusted_sword")[0]
        _set_item_state(item_repo, kit, {"used": False})
        _set_item_state(item_repo, sword, {"rust": "high"})

        app.execute_interaction(
            _player_id(loaded), _bench_id(loaded), "repair_with_kit",
            current_tick=WorldTick(5),
            acting_item_instance_id=kit,
            target_item_instance_id=sword,
        )

        # 修理キット側: used=true に書き換わって永続化されている
        kit_reloaded = item_repo.find_by_id(kit)
        assert kit_reloaded.state == {"used": True}

        # 剣側: rust=low + last_repaired_tick=5 に書き換わって永続化されている
        sword_reloaded = item_repo.find_by_id(sword)
        assert sword_reloaded.state == {"rust": "low", "last_repaired_tick": 5}

    def test_repair_blocked_when_kit_already_used(self, smithy) -> None:
        """1 度使った修理キットでは 2 度目の修理ができない (使う側の precondition 拒否)。"""
        loaded, _, inv_repo, item_repo, app = smithy
        kit = _instances_of(inv_repo, item_repo, loaded, "repair_kit")[0]
        sword = _instances_of(inv_repo, item_repo, loaded, "rusted_sword")[0]
        _set_item_state(item_repo, kit, {"used": False})
        _set_item_state(item_repo, sword, {"rust": "high"})

        # 1 回目は成功
        app.execute_interaction(
            _player_id(loaded), _bench_id(loaded), "repair_with_kit",
            current_tick=WorldTick(1),
            acting_item_instance_id=kit,
            target_item_instance_id=sword,
        )
        # 2 回目: 修理キットは used=true、剣は rust=low なので 2 重の理由で拒否される
        # (使う側 precondition と 使われる側 precondition のどちらが先に失敗するかは
        # 実装順依存だが、いずれにしても InteractionNotAllowed)
        with pytest.raises(InteractionNotAllowedException):
            app.execute_interaction(
                _player_id(loaded), _bench_id(loaded), "repair_with_kit",
                current_tick=WorldTick(2),
                acting_item_instance_id=kit,
                target_item_instance_id=sword,
            )

    def test_repair_blocked_when_sword_already_clean(self, smithy) -> None:
        """錆びていない剣には修理キットを使えない (使われる側の precondition 拒否)。"""
        loaded, _, inv_repo, item_repo, app = smithy
        kit = _instances_of(inv_repo, item_repo, loaded, "repair_kit")[0]
        sword = _instances_of(inv_repo, item_repo, loaded, "rusted_sword")[0]
        _set_item_state(item_repo, kit, {"used": False})
        # 剣は最初から rust=low (錆びていない)
        _set_item_state(item_repo, sword, {"rust": "low"})

        with pytest.raises(InteractionNotAllowedException):
            app.execute_interaction(
                _player_id(loaded), _bench_id(loaded), "repair_with_kit",
                current_tick=WorldTick(1),
                acting_item_instance_id=kit,
                target_item_instance_id=sword,
            )
        # 使う側 (修理キット) の状態は変わらない
        assert item_repo.find_by_id(kit).state == {"used": False}

    def test_same_instance_for_acting_and_target_rejected(self, smithy) -> None:
        """同じ item_instance_id を acting と target 両方に渡すと ApplicationException。"""
        loaded, _, inv_repo, item_repo, app = smithy
        kit = _instances_of(inv_repo, item_repo, loaded, "repair_kit")[0]
        _set_item_state(item_repo, kit, {"used": False})

        with pytest.raises(ApplicationException, match="同じ item_instance_id"):
            app.execute_interaction(
                _player_id(loaded), _bench_id(loaded), "repair_with_kit",
                current_tick=WorldTick(1),
                acting_item_instance_id=kit,
                target_item_instance_id=kit,
            )

    def test_target_item_instance_id_not_found_raises(self, smithy) -> None:
        """target_item_instance_id が repository に存在しないと ApplicationException。

        レビュー指摘 (HIGH): app service に「target が見つからない」分岐があるが
        テストで網羅されていなかった。リファクタで guard を消しても気付ける
        ようにレグレッションアンカーを置く。
        """
        loaded, _, inv_repo, item_repo, app = smithy
        kit = _instances_of(inv_repo, item_repo, loaded, "repair_kit")[0]
        _set_item_state(item_repo, kit, {"used": False})

        # 永続化されていない instance id を渡す
        ghost_id = ItemInstanceId(99999)
        assert item_repo.find_by_id(ghost_id) is None

        with pytest.raises(ApplicationException, match="target item instance"):
            app.execute_interaction(
                _player_id(loaded), _bench_id(loaded), "repair_with_kit",
                current_tick=WorldTick(1),
                acting_item_instance_id=kit,
                target_item_instance_id=ghost_id,
            )

    def test_target_required_but_none_provided_rejected(self, smithy) -> None:
        """TARGET_ITEM_INSTANCE_STATE precondition があるのに target が渡されないと拒否される。

        ドメイン側ガード (silent pass 回避) の挙動が app 経路でも保たれていることを保証。
        """
        loaded, _, inv_repo, item_repo, app = smithy
        kit = _instances_of(inv_repo, item_repo, loaded, "repair_kit")[0]
        _set_item_state(item_repo, kit, {"used": False})

        with pytest.raises(InteractionNotAllowedException):
            app.execute_interaction(
                _player_id(loaded), _bench_id(loaded), "repair_with_kit",
                current_tick=WorldTick(1),
                acting_item_instance_id=kit,
                # target_item_instance_id を渡さない
            )
        # 修理キットの状態は変わらない (precondition で弾かれて effect 未発火)
        assert item_repo.find_by_id(kit).state == {"used": False}

    def test_target_item_save_only_when_state_changed(self, smithy) -> None:
        """precondition で拒否された interaction では target item の save は呼ばれない。"""
        loaded, _, inv_repo, item_repo, app = smithy
        kit = _instances_of(inv_repo, item_repo, loaded, "repair_kit")[0]
        sword = _instances_of(inv_repo, item_repo, loaded, "rusted_sword")[0]
        # 修理キットを最初から used=true にして precondition を即落ちさせる
        _set_item_state(item_repo, kit, {"used": True})
        _set_item_state(item_repo, sword, {"rust": "high"})

        save_count = {"n": 0}
        original_save = item_repo.save

        def counting_save(agg):
            save_count["n"] += 1
            return original_save(agg)

        item_repo.save = counting_save  # type: ignore[assignment]

        with pytest.raises(InteractionNotAllowedException):
            app.execute_interaction(
                _player_id(loaded), _bench_id(loaded), "repair_with_kit",
                current_tick=WorldTick(1),
                acting_item_instance_id=kit,
                target_item_instance_id=sword,
            )
        # 拒否時はいずれも save されない
        assert save_count["n"] == 0
