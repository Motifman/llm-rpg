"""Phase 4-D-2 全体 (PR 1 + PR 2 + PR 3) の end-to-end 検証。

`data/scenarios/blessed_pilgrim_demo.json` を読み込み:

- 香 instance (state: {used: false}) で祭壇に祈祷を捧げる
  → 香 used=true / プレイヤー state prayed_today=true / prayed_at_tick 記録
- 同じ香で再度祈祷しようとする → ITEM_INSTANCE_STATE precondition 拒否
- 祈祷前に聖域の扉を開けようとする → PLAYER_STATE_IS precondition 拒否
- 祈祷後に聖域の扉を開ける → 通る
- 永続化: item_repository / player_status_repository から再読込しても state が残る

これにより以下が end-to-end で動くことを保証する:
- PlayerStatusAggregate.state field (Phase 4-D-2 PR 1)
- CHANGE_PLAYER_STATE / RECORD_PLAYER_STATE_TICK / PLAYER_STATE_IS (PR 2)
- SpotInteractionApplicationService への player_status_repo 配線 + save (PR 2)
- scenario JSON `players[].initial_state` の load + PlayerStatusAggregate への反映 (PR 3)
- アイテム × プレイヤー状態の複合作用 (1 つの interaction で両方を更新)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_graph.spot_interaction_application_service import (
    SpotInteractionApplicationService,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    grant_initial_items_to_inventory,
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
from ai_rpg_world.domain.player.aggregate.player_status_aggregate import (
    PlayerStatusAggregate,
)
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
from ai_rpg_world.domain.player.value_object.slot_id import SlotId
from ai_rpg_world.domain.player.value_object.stamina import Stamina
from ai_rpg_world.domain.player.value_object.stat_growth_factor import StatGrowthFactor
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
    / "blessed_pilgrim_demo.json"
)


def _build_player_status(player_id: PlayerId, spawn_spot_id: SpotId, initial_state: dict) -> PlayerStatusAggregate:
    """シナリオ load 結果から最小構成の PlayerStatusAggregate を組む。

    本物のゲーム server 側ではキャラ生成 / セーブデータ読み込みが間に挟まる
    が、デモテストでは scenario JSON の `players[].initial_state` が
    `PlayerStatusAggregate.state` までストレートに渡ることを示すのが目的なので、
    HP / MP 等は即値の素朴なデフォルトで埋める。
    """
    exp_table = ExpTable(100, 1.5)
    return PlayerStatusAggregate(
        player_id=player_id,
        base_stats=BaseStats(100, 50, 10, 10, 10, 0.05, 0.05),
        stat_growth_factor=StatGrowthFactor(1.0, 1.0, 1.0, 1.0, 1.0, 0.0, 0.0),
        exp_table=exp_table,
        growth=Growth(1, 0, exp_table),
        gold=Gold(0),
        hp=Hp(value=100, max_hp=100),
        mp=Mp(value=50, max_mp=50),
        stamina=Stamina(value=100, max_stamina=100),
        spot_navigation_state=PlayerSpotNavigationState.at_rest(spawn_spot_id),
        state=dict(initial_state),
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
        # Phase 4-D-2 PR 3: scenario JSON `players[].initial_state` を
        # PlayerStatusAggregate.state に渡してから永続化する。
        status_repo.save(
            _build_player_status(pid, spawn.spawn_spot_id, dict(spawn.initial_state))
        )
        inventory_repo.save(PlayerInventoryAggregate(player_id=pid))
        if spawn.initial_items:
            grant_initial_items_to_inventory(
                pid, spawn.initial_items,
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
    return loaded, interior_repo, inventory_repo, item_repo, status_repo, interaction_app


def _spot_id(loaded) -> SpotId:
    return SpotId.create(loaded.id_mapper.get_int("spot", "shrine"))


def _player_id(loaded) -> PlayerId:
    return PlayerId(loaded.player_spawns[0].player_id)


def _altar_id(loaded) -> SpotObjectId:
    return SpotObjectId.create(loaded.id_mapper.get_int("object", "altar"))


def _door_id(loaded) -> SpotObjectId:
    return SpotObjectId.create(loaded.id_mapper.get_int("object", "sanctum_door"))


def _incense_instances(inventory_repo, item_repo, loaded) -> list[ItemInstanceId]:
    """player_a の所持する香 instance ID を slot 順に返す。"""
    inv = inventory_repo.find_by_id(_player_id(loaded))
    spec_int = loaded.id_mapper.get_int("item_spec", "incense")
    out: list[ItemInstanceId] = []
    for i in range(inv.max_slots):
        iid = inv.get_item_instance_id_by_slot(SlotId(i))
        if iid is None:
            continue
        agg = item_repo.find_by_id(iid)
        if agg is not None and agg.item_spec.item_spec_id.value == spec_int:
            out.append(iid)
    return out


class TestBlessedPilgrimDemo:
    """Phase 4-D-2 全体: アイテム × プレイヤー状態の複合 interaction が end-to-end で動く。"""

    def test_initial_state_comes_from_scenario_json(self, shrine) -> None:
        """`players[].initial_state` の値が PlayerStatusAggregate.state に反映される。"""
        loaded, _, _, _, status_repo, _ = shrine
        status = status_repo.find_by_id(_player_id(loaded))
        assert status is not None
        assert status.state == {"prayed_today": False}

    def test_pray_writes_player_state_and_consumes_item(self, shrine) -> None:
        """祈祷を実行すると 香 → used=true / プレイヤー → prayed_today=true + tick 記録 が永続化される。"""
        loaded, _, inv_repo, item_repo, status_repo, app = shrine
        incense = _incense_instances(inv_repo, item_repo, loaded)[0]

        app.execute_interaction(
            _player_id(loaded), _altar_id(loaded), "pray",
            current_tick=WorldTick(5),
            acting_item_instance_id=incense,
        )

        # 香側: used=true に書き換わって永続化されている
        assert item_repo.find_by_id(incense).state == {"used": True}
        # プレイヤー側: prayed_today=true + prayed_at_tick=5 が永続化されている
        reloaded = status_repo.find_by_id(_player_id(loaded))
        assert reloaded.state == {"prayed_today": True, "prayed_at_tick": 5}

    def test_door_blocked_until_prayer(self, shrine) -> None:
        """祈祷前は PLAYER_STATE_IS で扉が拒否され、祈祷後は通る。"""
        loaded, _, inv_repo, item_repo, _, app = shrine
        incense = _incense_instances(inv_repo, item_repo, loaded)[0]

        # 祈祷前: 扉は PLAYER_STATE_IS で拒否
        with pytest.raises(InteractionNotAllowedException, match="祈祷を済ませていない"):
            app.execute_interaction(
                _player_id(loaded), _door_id(loaded), "enter_sanctum",
            )

        # 祈祷を済ませる
        app.execute_interaction(
            _player_id(loaded), _altar_id(loaded), "pray",
            current_tick=WorldTick(7),
            acting_item_instance_id=incense,
        )

        # 祈祷後: 扉が開く
        app.execute_interaction(
            _player_id(loaded), _door_id(loaded), "enter_sanctum",
        )

    def test_used_incense_cannot_pray_again(self, shrine) -> None:
        """1 度使った香で 2 度目の祈祷はできない (item × player state 複合 precondition の片方が拒否)。"""
        loaded, _, inv_repo, item_repo, _, app = shrine
        incense = _incense_instances(inv_repo, item_repo, loaded)[0]

        app.execute_interaction(
            _player_id(loaded), _altar_id(loaded), "pray",
            current_tick=WorldTick(3),
            acting_item_instance_id=incense,
        )

        # 同じ香 instance で 2 度目: ITEM_INSTANCE_STATE used:false に違反。
        # match は scenario JSON 側の failure_message と完全一致させる
        # (将来 message を変えたとき、誤った代替パターンに silent pass しないため)
        with pytest.raises(InteractionNotAllowedException, match="焚き切"):
            app.execute_interaction(
                _player_id(loaded), _altar_id(loaded), "pray",
                current_tick=WorldTick(4),
                acting_item_instance_id=incense,
            )
