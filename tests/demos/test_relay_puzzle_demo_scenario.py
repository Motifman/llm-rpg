"""協力ギミック #15 (役割分担リレー) の最小デモシナリオの end-to-end 検証。

`data/scenarios/relay_puzzle_demo.json` を読み込み、ReactivePassageBindingStageService
が tick 毎に正しく predicate を評価して passage state を切り替えるかを確認する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai_rpg_world.application.world_graph.reactive_object_state_binding_stage_service import (
    ReactiveObjectStateBindingStageService,
)
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
    passage_stage = ReactivePassageBindingStageService(
        bindings=loaded.reactive_passage_bindings,
        spot_graph_repository=spot_graph_repo,
        condition_evaluator=evaluator,
    )
    object_stage = ReactiveObjectStateBindingStageService(
        bindings=loaded.reactive_object_state_bindings,
        spot_graph_repository=spot_graph_repo,
        spot_interior_repository=interior_repo,
        condition_evaluator=evaluator,
    )

    def run_tick(tick: int) -> None:
        """passage → object の順で 1 tick 走らせる (本番 simulation と同じ順序)。

        本番の ``SpotGraphSimulationApplicationService._tick_impl`` も
        ``reactive_binding_stage`` (passages) → ``reactive_object_state_stage``
        の順で呼ぶ。passage stage が現在の object state を読んで扉に反映、
        object stage が PLAYER_AT_SPOT 等を読んで panel の電源を auto-off
        する。結果として「A が出る → 次 tick でも扉はまだ OPEN (passage が
        先に走るので) → object stage が power_off → さらに次 tick で扉
        LOCKED」という 1 tick ラグが発生する。本番の挙動を素直に反映する。
        """
        passage_stage.run(WorldTick(tick))
        object_stage.run(WorldTick(tick))

    return loaded, spot_graph_repo, interior_repo, run_tick


def _cid(loaded, string_id: str) -> ConnectionId:
    return ConnectionId.create(loaded.id_mapper.get_int("connection", string_id))


def _spot(loaded, string_id: str) -> SpotId:
    return SpotId.create(loaded.id_mapper.get_int("spot", string_id))


def _set_panel_power(interior_repo, loaded, value: bool) -> None:
    """テスト用ヘルパー: control_panel.state.power_on を直接書き換える。

    LLM ツール経由の interaction service を使わずに reactive_binding の
    動作だけを検証するため、interior の SpotObject state を直接更新する。
    """
    spot_id = _spot(loaded, "control_room")
    panel_oid = SpotObjectId.create(loaded.id_mapper.get_int("object", "control_panel"))
    interior = interior_repo.find_by_spot_id(spot_id)
    assert interior is not None
    panel = interior.get_object(panel_oid)
    assert panel is not None, "control_panel object missing from interior"
    new_state = dict(panel.state)
    new_state["power_on"] = value
    updated_panel = panel.with_state(new_state)
    updated_interior = interior.replace_object(updated_panel)
    interior_repo.save(spot_id, updated_interior)


class TestRelayPuzzleDemoScenario:
    """relay_puzzle_demo.json が #15 役割分担リレーの仕様通りに動く。

    新メカニクス (control_panel object 経由):
    - 操作盤の電源 ON で扉が OPEN になる
    - 電源 OFF or 制御室から誰も居なくなると次 tick で電源 auto-off
    - 電源 auto-off の次 tick で扉が LOCKED に戻る (1 tick lag)
    """

    def test_door_stays_locked_until_panel_powered_on(self, relay_puzzle) -> None:
        """初期状態 (panel power_on=false) では tick を回しても扉は LOCKED のまま。"""
        loaded, repo, _interior_repo, run_tick = relay_puzzle
        cid = _cid(loaded, "corridor_to_vault")
        # spawn 直後は LOCKED
        assert repo.find_graph().get_connection(cid).passage.state == "LOCKED"
        run_tick(1)
        # panel 未操作なので power_on=false → 扉 LOCKED のまま
        assert repo.find_graph().get_connection(cid).passage.state == "LOCKED"

    def test_door_opens_after_panel_powered_on(self, relay_puzzle) -> None:
        """A が操作盤の電源を入れると、次 tick で扉が OPEN になる。"""
        loaded, repo, interior_repo, run_tick = relay_puzzle
        cid = _cid(loaded, "corridor_to_vault")

        _set_panel_power(interior_repo, loaded, value=True)
        run_tick(1)
        assert repo.find_graph().get_connection(cid).passage.state == "OPEN"

    def test_door_relocks_after_a_leaves_control_room(self, relay_puzzle) -> None:
        """A が制御室から出ると panel が auto-off → 次 tick で扉 LOCKED。

        ステージ順序により 1 tick lag が発生する: A 退室直後の同 tick では
        扉はまだ OPEN (passage stage が先に評価)。続く tick で object stage
        が反映済の power_on=false を passage stage が読んで LOCKED へ。
        """
        loaded, repo, interior_repo, run_tick = relay_puzzle
        cid = _cid(loaded, "corridor_to_vault")

        # A 在室 + panel ON で扉 OPEN
        _set_panel_power(interior_repo, loaded, value=True)
        run_tick(1)
        assert repo.find_graph().get_connection(cid).passage.state == "OPEN"

        # A を制御室から廊下へ teleport (object stage が NOT PLAYER_AT_SPOT を見て auto-off する)
        a_id = next(s.player_id for s in loaded.player_spawns if s.string_id == "player_a")
        graph = repo.find_graph()
        graph.unplace_entity(EntityId.create(a_id))
        graph.place_entity(EntityId.create(a_id), _spot(loaded, "corridor"))
        repo.save(graph)

        # 次 tick: object stage が panel power_on=false にする
        run_tick(2)
        # さらに次 tick: passage stage が power_on=false を読んで LOCKED
        run_tick(3)
        assert repo.find_graph().get_connection(cid).passage.state == "LOCKED"

    def test_reverse_connection_auto_mirrors_predicate(self, relay_puzzle) -> None:
        """`apply_to_reverse` 既定で、逆方向接続も同じ predicate に追従する。"""
        loaded, repo, interior_repo, run_tick = relay_puzzle
        rev_cid = _cid(loaded, "corridor_to_vault__reverse")
        _set_panel_power(interior_repo, loaded, value=True)
        run_tick(1)
        assert repo.find_graph().get_connection(rev_cid).passage.state == "OPEN"

    def test_b_in_control_room_keeps_panel_active(self, relay_puzzle) -> None:
        """A が出ても B が制御室に居れば panel auto-off せず扉は OPEN を維持。

        旧 PLAYER_AT_SPOT メカニクスの「誰かが居れば」をオブジェクトベース
        メカニクスでも保持しているかの確認 (協力プレイの spirit)。
        """
        loaded, repo, interior_repo, run_tick = relay_puzzle
        cid = _cid(loaded, "corridor_to_vault")

        _set_panel_power(interior_repo, loaded, value=True)
        run_tick(1)
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

        run_tick(2)
        run_tick(3)
        # B が制御室に居るので panel auto-off は発火せず、扉は OPEN のまま
        assert repo.find_graph().get_connection(cid).passage.state == "OPEN"
