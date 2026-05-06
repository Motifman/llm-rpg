"""環境 → アイテム入手の最小デモ end-to-end 検証。

`data/scenarios/foragable_bush_demo.json` を読み込み、

1. プレイヤーが harvest interaction で OBJECT_STATE precondition を
   通過し GIVE_ITEM で野いちごを入手する
2. CHANGE_OBJECT_STATE / RECORD_OBJECT_STATE_TICK で茂みが
   available=false + last_harvest_tick=採取時 tick になる
3. ReactiveObjectStateBinding が 8 tick 経過後に available=true に
   戻し、再採取が可能になる

の流れを保証する。新 primitive ゼロ — Phase 1-β として「環境から
アイテムが供給される」単方向の作用が既存基盤だけで書けることを実証。
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
    / "foragable_bush_demo.json"
)


@pytest.fixture
def forage():
    """採集者プレイヤーと未収穫のベリー茂みを初期化したコンテキストを返す。"""
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
        inventory_repo.save(PlayerInventoryAggregate(player_id=PlayerId(spawn.player_id)))

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
    return SpotId.create(loaded.id_mapper.get_int("spot", "forest_clearing"))


def _bush_id(loaded) -> SpotObjectId:
    return SpotObjectId.create(loaded.id_mapper.get_int("object", "berry_bush"))


def _player_id(loaded) -> PlayerId:
    return PlayerId(loaded.player_spawns[0].player_id)


def _bush_state(interior_repo, loaded) -> dict:
    interior = interior_repo.find_by_spot_id(_spot_id(loaded))
    obj = next(o for o in interior.objects if o.object_id == _bush_id(loaded))
    return obj.state


def _berry_count(inventory_repo, item_repo, loaded) -> int:
    """所持している野いちご (instance) 数を返す。

    `collect_owned_item_spec_ids_from_inventory` は frozenset を返して
    重複所持数が消えるため、ここでは slot を直接列挙してカウントする。
    """
    berry_spec_int = loaded.id_mapper.get_int("item_spec", "wild_berry")
    inv = inventory_repo.find_by_id(_player_id(loaded))
    n = 0
    for i in range(inv.max_slots):
        iid = inv.get_item_instance_id_by_slot(SlotId(i))
        if iid is None:
            continue
        agg = item_repo.find_by_id(iid)
        if agg is not None and agg.item_spec.item_spec_id.value == berry_spec_int:
            n += 1
    return n


class TestForagableBushDemoScenario:
    """foragable_bush_demo.json が environment → item の単方向作用を保証する。"""

    def test_initial_state_bush_is_available_player_has_no_berry(self, forage) -> None:
        """初期: 茂みは available=true、プレイヤーは野いちごを持っていない。"""
        loaded, interior_repo, inventory_repo, item_repo, _, _ = forage
        assert _bush_state(interior_repo, loaded)["available"] is True
        assert _berry_count(inventory_repo, item_repo, loaded) == 0

    def test_harvest_grants_berry_and_depletes_bush(self, forage) -> None:
        """harvest で野いちご 1 個を入手し、茂みは available=false + last_harvest_tick 記録になる。"""
        loaded, interior_repo, inventory_repo, item_repo, app, _ = forage
        app.execute_interaction(
            _player_id(loaded), _bush_id(loaded), "harvest",
            current_tick=WorldTick(3),
        )
        assert _berry_count(inventory_repo, item_repo, loaded) == 1
        s = _bush_state(interior_repo, loaded)
        assert s["available"] is False
        assert s["last_harvest_tick"] == 3

    def test_harvest_blocked_when_unavailable(self, forage) -> None:
        """available=false の茂みに harvest しようとすると InteractionNotAllowedException で拒否。"""
        loaded, _, _, _, app, _ = forage
        # 1 度目の harvest で available=false に
        app.execute_interaction(
            _player_id(loaded), _bush_id(loaded), "harvest", current_tick=WorldTick(3),
        )
        with pytest.raises(InteractionNotAllowedException):
            app.execute_interaction(
                _player_id(loaded), _bush_id(loaded), "harvest", current_tick=WorldTick(4),
            )

    def test_bush_regrows_after_offset_and_allows_second_harvest(self, forage) -> None:
        """ticks_offset (=8) tick 経過すると binding が available=true に戻し、再採取が成立する。"""
        loaded, interior_repo, inventory_repo, item_repo, app, binding_stage = forage
        # 1 回目
        app.execute_interaction(
            _player_id(loaded), _bush_id(loaded), "harvest", current_tick=WorldTick(3),
        )
        # tick 4-10: 経過 1-7 < 8 なので available=false 維持
        for t in range(4, 11):
            binding_stage.run(WorldTick(t))
            assert _bush_state(interior_repo, loaded)["available"] is False, (
                f"tick={t} で早期再生"
            )
        # tick 11: 3+8=11、predicate true → available=true
        binding_stage.run(WorldTick(11))
        assert _bush_state(interior_repo, loaded)["available"] is True

        # 2 回目 harvest 成功
        app.execute_interaction(
            _player_id(loaded), _bush_id(loaded), "harvest", current_tick=WorldTick(12),
        )
        assert _berry_count(inventory_repo, item_repo, loaded) == 2
        assert _bush_state(interior_repo, loaded)["available"] is False
        assert _bush_state(interior_repo, loaded)["last_harvest_tick"] == 12
