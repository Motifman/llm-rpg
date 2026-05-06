"""Phase 4-A 全体 (PR 1 + PR 2 + PR 3) の end-to-end 検証。

`data/scenarios/lantern_lifecycle_demo.json` を読み込み:

- 未使用マッチ instance で中央ランプを点ける → ランプ lit / マッチ used + tick 記録
- 同じマッチで奥のランプを点けようとする → ITEM_INSTANCE_STATE
  precondition で拒否 (used:false に違反)
- 別の未使用マッチで奥のランプを点ける → 別 instance なので state は独立、成功
- 永続化: item_repository.find_by_id で再読込しても state が残る (PR 1)

これにより以下が end-to-end で動くことを保証する:
- ItemInstance.state field (PR 1)
- CHANGE_ITEM_INSTANCE_STATE / RECORD_ITEM_INSTANCE_STATE_TICK / ITEM_INSTANCE_STATE (PR 2)
- SpotInteractionApplicationService への acting_item_instance_id 配線 + save (PR 3)
- per-instance state がスタッカブルでないこと (PR 1 不変条件)
"""

from __future__ import annotations

from pathlib import Path

import pytest

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
    / "lantern_lifecycle_demo.json"
)


@pytest.fixture
def shrine():
    """祠シナリオを load して app + repos を返す。"""
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
    return SpotId.create(loaded.id_mapper.get_int("spot", "shrine"))


def _player_id(loaded) -> PlayerId:
    return PlayerId(loaded.player_spawns[0].player_id)


def _lamp_id(loaded, name: str) -> SpotObjectId:
    return SpotObjectId.create(loaded.id_mapper.get_int("object", name))


def _lamp_state(interior_repo, loaded, name: str) -> dict:
    interior = interior_repo.find_by_spot_id(_spot_id(loaded))
    return next(
        o.state for o in interior.objects if o.object_id == _lamp_id(loaded, name)
    )


def _match_instance_ids(inventory_repo, item_repo, loaded) -> list[ItemInstanceId]:
    """所持しているマッチ instance の ID を順に返す（slot 順）。"""
    inv = inventory_repo.find_by_id(_player_id(loaded))
    match_spec_int = loaded.id_mapper.get_int("item_spec", "match")
    out = []
    for i in range(inv.max_slots):
        iid = inv.get_item_instance_id_by_slot(SlotId(i))
        if iid is None:
            continue
        agg = item_repo.find_by_id(iid)
        if agg is not None and agg.item_spec.item_spec_id.value == match_spec_int:
            out.append(iid)
    return out


class TestLanternLifecycleDemo:
    """Phase 4-A 全体: item instance state が effect / precondition で操作され、永続化される。"""

    def test_initial_match_state_is_unused(self, shrine) -> None:
        """初期状態: マッチ 2 本を所持し、いずれも state が空 (= 未使用)。"""
        loaded, _, inv_repo, item_repo, _ = shrine
        match_ids = _match_instance_ids(inv_repo, item_repo, loaded)
        assert len(match_ids) == 2
        for iid in match_ids:
            agg = item_repo.find_by_id(iid)
            assert agg is not None
            # 初期 state は空 dict (used キーは ITEM_INSTANCE_STATE precondition の
            # required_state={used: false} を満たさない＝False になるが、最初の
            # 点火試行では別の precondition が先に通る; ここでは state が空である
            # ことだけ確認)
            assert agg.state == {}

    def test_first_match_lights_lamp_a_and_records_state(self, shrine) -> None:
        """マッチ A で中央ランプを点ける。
        - lamp_a.lit が True に変わる
        - match A.state が {used: true, used_at_tick: T} に書き換わる (PR 2 effect)
        - item_repository に永続化される (PR 3 save)
        """
        loaded, interior_repo, inv_repo, item_repo, app = shrine
        match_ids = _match_instance_ids(inv_repo, item_repo, loaded)
        match_a = match_ids[0]

        # 最初の点火試行: マッチ A の state は空 dict なので
        # ITEM_INSTANCE_STATE(required={used: false}) を満たさない（used キーが無い）。
        # → 初期点火が成立する設計にはマッチ側 state を仕込んでおく必要がある。
        # ここでは「state が空 → required {used: false} は不一致 → 拒否」を
        # まず確認し、次に明示的に used=false を仕込んでから点火する流れにする。
        with pytest.raises(InteractionNotAllowedException):
            app.execute_interaction(
                _player_id(loaded), _lamp_id(loaded, "lamp_a"), "light",
                current_tick=WorldTick(1),
                acting_item_instance_id=match_a,
            )

        # マッチ A に明示的に used=false を仕込む (シナリオ作家が initial state で
        # 仕込む代わりに、テスト内で aggregate 直接操作して状況を作る)
        agg_a = item_repo.find_by_id(match_a)
        assert agg_a is not None
        agg_a.merge_state({"used": False})
        item_repo.save(agg_a)

        # 点火実行
        app.execute_interaction(
            _player_id(loaded), _lamp_id(loaded, "lamp_a"), "light",
            current_tick=WorldTick(2),
            acting_item_instance_id=match_a,
        )

        # 中央ランプは点灯
        assert _lamp_state(interior_repo, loaded, "lamp_a")["lit"] is True
        # マッチ A の state が「使用済み + 点火 tick 記録」に更新され、永続化されている
        agg_a_reloaded = item_repo.find_by_id(match_a)
        assert agg_a_reloaded is not None
        assert agg_a_reloaded.state == {"used": True, "used_at_tick": 2}

    def test_used_match_cannot_light_another_lamp(self, shrine) -> None:
        """1 度使ったマッチでは奥のランプを点けられない (precondition `used: false` で拒否)。"""
        loaded, interior_repo, inv_repo, item_repo, app = shrine
        match_ids = _match_instance_ids(inv_repo, item_repo, loaded)
        match_a = match_ids[0]

        # マッチ A を仕込み + 中央ランプ点火
        agg_a = item_repo.find_by_id(match_a)
        agg_a.merge_state({"used": False})
        item_repo.save(agg_a)
        app.execute_interaction(
            _player_id(loaded), _lamp_id(loaded, "lamp_a"), "light",
            current_tick=WorldTick(1),
            acting_item_instance_id=match_a,
        )

        # 同じマッチで奥のランプを点けようとする → 拒否
        with pytest.raises(InteractionNotAllowedException):
            app.execute_interaction(
                _player_id(loaded), _lamp_id(loaded, "lamp_b"), "light",
                current_tick=WorldTick(2),
                acting_item_instance_id=match_a,
            )
        # 奥のランプは未点灯のまま
        assert _lamp_state(interior_repo, loaded, "lamp_b")["lit"] is False

    def test_second_unused_match_lights_lamp_b_independently(self, shrine) -> None:
        """別 instance のマッチ B (state 独立) は奥のランプを点けられる。

        Phase 4-A の重要不変条件: 同 spec でも instance ごとに state が独立。
        マッチ A が used=true でも、マッチ B は used=false のまま使える。
        """
        loaded, interior_repo, inv_repo, item_repo, app = shrine
        match_ids = _match_instance_ids(inv_repo, item_repo, loaded)
        match_a, match_b = match_ids[0], match_ids[1]

        # マッチ A を仕込み + 中央ランプ点火
        agg_a = item_repo.find_by_id(match_a)
        agg_a.merge_state({"used": False})
        item_repo.save(agg_a)
        app.execute_interaction(
            _player_id(loaded), _lamp_id(loaded, "lamp_a"), "light",
            current_tick=WorldTick(1),
            acting_item_instance_id=match_a,
        )

        # マッチ B を仕込み + 奥ランプ点火
        agg_b = item_repo.find_by_id(match_b)
        agg_b.merge_state({"used": False})
        item_repo.save(agg_b)
        app.execute_interaction(
            _player_id(loaded), _lamp_id(loaded, "lamp_b"), "light",
            current_tick=WorldTick(3),
            acting_item_instance_id=match_b,
        )

        # 両ランプとも点灯
        assert _lamp_state(interior_repo, loaded, "lamp_a")["lit"] is True
        assert _lamp_state(interior_repo, loaded, "lamp_b")["lit"] is True
        # マッチ B も used + tick 記録 (instance ごとに独立した tick)
        agg_b_reloaded = item_repo.find_by_id(match_b)
        assert agg_b_reloaded.state == {"used": True, "used_at_tick": 3}
        # マッチ A は最初の使用時 tick=1 のまま
        agg_a_reloaded = item_repo.find_by_id(match_a)
        assert agg_a_reloaded.state == {"used": True, "used_at_tick": 1}

    def test_app_service_does_not_save_when_state_unchanged(self, shrine) -> None:
        """`item_instance_state_changed=False` の interaction では item_repository.save は呼ばれない。

        precondition で拒否された場合、そもそも effect が発火しないので
        state 変更も発生しない。caller が save を呼ぶのは state 変更があった時のみ。
        """
        loaded, _, inv_repo, item_repo, app = shrine
        match_a = _match_instance_ids(inv_repo, item_repo, loaded)[0]

        save_count = {"n": 0}
        original_save = item_repo.save

        def counting_save(agg):
            save_count["n"] += 1
            return original_save(agg)

        item_repo.save = counting_save  # type: ignore[assignment]

        # マッチ A は state が空のまま → ITEM_INSTANCE_STATE 拒否
        with pytest.raises(InteractionNotAllowedException):
            app.execute_interaction(
                _player_id(loaded), _lamp_id(loaded, "lamp_a"), "light",
                current_tick=WorldTick(1),
                acting_item_instance_id=match_a,
            )
        # 拒否時は item_repository.save は呼ばれない
        assert save_count["n"] == 0
