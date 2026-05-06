"""協力ギミック #15 (役割分担リレー) の最小デモシナリオの end-to-end 検証。

`data/scenarios/relay_puzzle_demo.json` を読み込み、ReactivePassageBindingStageService
が tick 毎に正しく predicate を評価して passage state を切り替えるかを確認する。
"""

from __future__ import annotations

from pathlib import Path

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


class TestRelayPuzzleDemoScenario:
    """relay_puzzle_demo.json が #15 役割分担リレーの仕様通りに動く。"""

    def _setup(self):
        loaded = ScenarioLoader().load_from_file(SCENARIO_PATH)
        graph = loaded.graph
        # プレイヤー spawn を反映
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

        # 各プレイヤーの inventory aggregate を空で登録（HAS_ITEM 条件はないが
        # 評価器の規約に合わせる）
        from ai_rpg_world.domain.player.value_object.player_id import PlayerId
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

    def test_initial_door_locked_with_a_at_control_room_changes_to_open_after_first_tick(self) -> None:
        """A が制御室に居る初期状態で 1 tick 後に金庫扉が OPEN になる。"""
        loaded, repo, stage = self._setup()
        cid_str = "corridor_to_vault"
        cid = ConnectionId.create(loaded.id_mapper.get_int("connection", cid_str))
        # spawn 直後（stage 未実行）は LOCKED のまま
        assert repo.find_graph().get_connection(cid).passage.state == "LOCKED"

        stage.run(WorldTick(1))
        assert repo.find_graph().get_connection(cid).passage.state == "OPEN"

    def test_door_relocks_when_a_leaves_control_room(self) -> None:
        """A が制御室を離れた状態を作って tick を回すと扉が LOCKED に戻る。"""
        loaded, repo, stage = self._setup()
        cid_str = "corridor_to_vault"
        cid = ConnectionId.create(loaded.id_mapper.get_int("connection", cid_str))

        # 初回 tick で OPEN になる
        stage.run(WorldTick(1))
        assert repo.find_graph().get_connection(cid).passage.state == "OPEN"

        # A (player_a の entity_id) を制御室から corridor へ移動
        player_a_id = next(s.player_id for s in loaded.player_spawns if s.string_id == "player_a")
        graph = repo.find_graph()
        # presence 直接操作で移動を表現（move_entity API はアイテム/フラグを要求するため、
        # ここでは reactive 評価が PLAYER_AT_SPOT(control_room)=False になることだけ
        # 検証したい）
        from ai_rpg_world.domain.world.value_object.spot_id import SpotId
        from ai_rpg_world.domain.world_graph.value_object.spot_presence import SpotPresence
        control_spot = SpotId.create(loaded.id_mapper.get_int("spot", "control_room"))
        corridor_spot = SpotId.create(loaded.id_mapper.get_int("spot", "corridor"))
        eid = EntityId.create(player_a_id)
        # 内部 presence を直接書き換え（テスト用近道）
        graph._presences[control_spot] = SpotPresence.empty(control_spot)
        graph._presences[corridor_spot] = graph._presences.get(
            corridor_spot, SpotPresence.empty(corridor_spot)
        ).add(eid)
        graph._entity_spot[eid] = corridor_spot
        repo.save(graph)

        stage.run(WorldTick(2))
        assert repo.find_graph().get_connection(cid).passage.state == "LOCKED"

    def test_reverse_connection_also_responds_to_predicate(self) -> None:
        """逆方向の corridor_to_vault__reverse も A の在室で OPEN になる。"""
        loaded, repo, stage = self._setup()
        rev_cid = ConnectionId.create(
            loaded.id_mapper.get_int("connection", "corridor_to_vault__reverse")
        )
        stage.run(WorldTick(1))
        assert repo.find_graph().get_connection(rev_cid).passage.state == "OPEN"
