"""協力ギミック #15 (役割分担リレー) の最小デモシナリオの end-to-end 検証。

`data/scenarios/relay_puzzle_demo.json` を読み込み、ReactivePassageBindingStageService
が tick 毎に正しく predicate を評価して passage state を切り替えるかを確認する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_graph.reactive_passage_binding_stage_service import (
    ReactivePassageBindingStageService,
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
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
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
    Path(__file__).resolve().parents[2] / "data" / "scenarios" / "relay_puzzle_demo.json"
)


@pytest.fixture
def relay_puzzle():
    """シナリオを読み込んで stage と repo, mapper を返す。"""
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

    evaluator = ScenarioConditionEvaluator(
        world_flag_state=MutableWorldFlagState(),
        spot_interior_repository=interior_repo,
        player_status_repository=status_repo,
        player_inventory_repository=inventory_repo,
        item_repository=item_repo,
    )
    stage = ReactivePassageBindingStageService(
        bindings=loaded.reactive_passage_bindings,
        spot_graph_repository=spot_graph_repo,
        condition_evaluator=evaluator,
    )
    return loaded, spot_graph_repo, stage


def _cid(loaded, string_id: str) -> ConnectionId:
    return ConnectionId.create(loaded.id_mapper.get_int("connection", string_id))


def _spot(loaded, string_id: str) -> SpotId:
    return SpotId.create(loaded.id_mapper.get_int("spot", string_id))


class TestRelayPuzzleDemoScenario:
    """relay_puzzle_demo.json が #15 役割分担リレーの仕様通りに動く。"""

    def test_door_opens_after_first_tick(self, relay_puzzle) -> None:
        """A 在室の初期状態で 1 tick 走らせると金庫扉が OPEN になる。"""
        loaded, repo, stage = relay_puzzle
        cid = _cid(loaded, "corridor_to_vault")
        # spawn 直後（stage 未実行）は LOCKED のまま
        assert repo.find_graph().get_connection(cid).passage.state == "LOCKED"
        stage.run(WorldTick(1))
        assert repo.find_graph().get_connection(cid).passage.state == "OPEN"

    def test_door_relocks_when_a_leaves_control_room(self, relay_puzzle) -> None:
        """A が制御室を離れたら次 tick で扉が LOCKED に戻る。"""
        loaded, repo, stage = relay_puzzle
        cid = _cid(loaded, "corridor_to_vault")

        stage.run(WorldTick(1))
        assert repo.find_graph().get_connection(cid).passage.state == "OPEN"

        # A を制御室から廊下へ teleport（テスト用 unplace + place）
        player_a_id = next(s.player_id for s in loaded.player_spawns if s.string_id == "player_a")
        eid = EntityId.create(player_a_id)
        graph = repo.find_graph()
        graph.unplace_entity(eid)
        graph.place_entity(eid, _spot(loaded, "corridor"))
        repo.save(graph)

        stage.run(WorldTick(2))
        assert repo.find_graph().get_connection(cid).passage.state == "LOCKED"

    def test_reverse_connection_auto_mirrors_predicate(self, relay_puzzle) -> None:
        """`apply_to_reverse` 既定で、逆方向接続も同じ predicate に追従する。"""
        loaded, repo, stage = relay_puzzle
        rev_cid = _cid(loaded, "corridor_to_vault__reverse")
        stage.run(WorldTick(1))
        assert repo.find_graph().get_connection(rev_cid).passage.state == "OPEN"

    def test_b_in_control_room_also_satisfies_predicate(self, relay_puzzle) -> None:
        """A が離れても、B が制御室に入れば predicate が成立し扉は OPEN のまま。

        現在の PLAYER_AT_SPOT 条件は「誰かが居る」judging。シナリオ description も
        その semantics に合わせて書いている。後続で entity 限定判定を入れたいなら
        新たな condition_type を導入する想定。
        """
        loaded, repo, stage = relay_puzzle
        cid = _cid(loaded, "corridor_to_vault")
        stage.run(WorldTick(1))
        assert repo.find_graph().get_connection(cid).passage.state == "OPEN"

        # A を退去させ、B を制御室に移動
        graph = repo.find_graph()
        a_id = next(s.player_id for s in loaded.player_spawns if s.string_id == "player_a")
        b_id = next(s.player_id for s in loaded.player_spawns if s.string_id == "player_b")
        graph.unplace_entity(EntityId.create(a_id))
        graph.place_entity(EntityId.create(a_id), _spot(loaded, "corridor"))
        graph.unplace_entity(EntityId.create(b_id))
        graph.place_entity(EntityId.create(b_id), _spot(loaded, "control_room"))
        repo.save(graph)

        stage.run(WorldTick(2))
        # B が制御室に居るので OPEN のまま
        assert repo.find_graph().get_connection(cid).passage.state == "OPEN"
