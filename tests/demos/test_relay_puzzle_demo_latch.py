"""relay_puzzle に追加した latch mechanism (扉固定スイッチ) の挙動テスト。

意図 (#188 Step 2):
- 元の reactive_passage_binding は ``OBJECT_STATE(control_panel, power_on=true)``
  だけが扉開閉条件で、operator が制御室を離れると必ず扉が閉まる構造だった
- ``door_latch.engaged=true`` を **OR 条件** として追加することで、
  「金庫室到達者がスイッチを押せば、operator が離れても扉が開いたまま」という
  正規の relay 解法を成立させる

検証する不変条件:
- 初期状態: 扉は LOCKED
- power_on=true (latch off) → 扉 OPEN (既存の挙動が壊れていない)
- power_off + latch off → 扉 LOCKED
- power_off + **latch engaged** → 扉 OPEN ← latch の新機能
- latch off に戻すと再び LOCKED
- 両方 on でも当然 OPEN
"""

from __future__ import annotations

from pathlib import Path

from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId
from demos.escape_game.escape_game_runtime import create_escape_game_runtime


_SCENARIO_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "relay_puzzle_demo.json"
)


def _setup():
    rt = create_escape_game_runtime(_SCENARIO_PATH)
    mapper = rt.scenario.id_mapper
    control_room = SpotId(mapper.get_int("spot", "control_room"))
    vault = SpotId(mapper.get_int("spot", "vault"))
    control_panel = SpotObjectId(mapper.get_int("object", "control_panel"))
    door_latch = SpotObjectId(mapper.get_int("object", "door_latch"))
    corridor_to_vault = ConnectionId(mapper.get_int("connection", "corridor_to_vault"))
    graph = rt._spot_graph_repo.find_graph()
    return rt, graph, control_room, vault, control_panel, door_latch, corridor_to_vault


def _set_panel_power(rt, control_room, control_panel, on: bool) -> None:
    interior = rt._spot_interior_repo.find_by_spot_id(control_room)
    panel = next(o for o in interior.objects if o.object_id == control_panel)
    rt._spot_interior_repo.save(
        control_room, interior.replace_object(panel.with_state({"power_on": on}))
    )


def _set_latch(rt, vault, door_latch, engaged: bool) -> None:
    interior = rt._spot_interior_repo.find_by_spot_id(vault)
    latch = next(o for o in interior.objects if o.object_id == door_latch)
    rt._spot_interior_repo.save(
        vault, interior.replace_object(latch.with_state({"engaged": engaged}))
    )


class TestRelayPuzzleLatchMechanism:
    """latch mechanism の挙動。"""

    def test_initial_state_door_is_locked(self) -> None:
        """初期 (power_off, latch off) で扉は LOCKED。"""
        rt, graph, _control_room, _vault, _panel, _latch, conn_id = _setup()
        assert graph.get_connection(conn_id).passage.traversable is False

    def test_power_on_only_opens_door_existing_behavior(self) -> None:
        """既存挙動: power_on=true で扉 OPEN (latch は false のまま)。"""
        rt, graph, cr, _vault, panel, _latch, conn = _setup()
        _set_panel_power(rt, cr, panel, True)
        rt.advance_tick()
        assert graph.get_connection(conn).passage.traversable is True

    def test_power_off_and_latch_off_locks_door(self) -> None:
        """両方 off で扉 LOCKED。"""
        rt, graph, cr, vault, panel, latch, conn = _setup()
        _set_panel_power(rt, cr, panel, False)
        _set_latch(rt, vault, latch, False)
        rt.advance_tick()
        assert graph.get_connection(conn).passage.traversable is False

    def test_latch_engaged_opens_door_even_without_power(self) -> None:
        """**latch の核心機能**: power_off でも latch=true なら扉 OPEN。"""
        rt, graph, cr, vault, panel, latch, conn = _setup()
        _set_panel_power(rt, cr, panel, False)
        _set_latch(rt, vault, latch, True)
        rt.advance_tick()
        assert graph.get_connection(conn).passage.traversable is True, (
            "latch engaged の OR 条件で扉が開かないと latch mechanism が機能していない"
        )

    def test_latch_disengaged_locks_door_again(self) -> None:
        """latch を off に戻すと再び LOCKED (power_off の場合)。"""
        rt, graph, cr, vault, panel, latch, conn = _setup()
        _set_panel_power(rt, cr, panel, False)
        _set_latch(rt, vault, latch, True)
        rt.advance_tick()
        assert graph.get_connection(conn).passage.traversable is True
        _set_latch(rt, vault, latch, False)
        rt.advance_tick()
        assert graph.get_connection(conn).passage.traversable is False

    def test_both_on_keeps_door_open(self) -> None:
        """power_on=true AND latch=true でも当然 OPEN。"""
        rt, graph, cr, vault, panel, latch, conn = _setup()
        _set_panel_power(rt, cr, panel, True)
        _set_latch(rt, vault, latch, True)
        rt.advance_tick()
        assert graph.get_connection(conn).passage.traversable is True


class TestRelayPuzzleLatchObjectStructure:
    """door_latch オブジェクトの存在と仕様。"""

    def test_door_latch_exists_in_vault(self) -> None:
        """金庫室の interior に door_latch が存在する。"""
        rt, _, _, vault, _, latch, _ = _setup()
        interior = rt._spot_interior_repo.find_by_spot_id(vault)
        latch_obj = next(
            (o for o in interior.objects if o.object_id == latch), None
        )
        assert latch_obj is not None
        assert latch_obj.name == "扉固定スイッチ"

    def test_door_latch_initial_state_is_disengaged(self) -> None:
        """初期 state は engaged=false。"""
        rt, _, _, vault, _, latch, _ = _setup()
        interior = rt._spot_interior_repo.find_by_spot_id(vault)
        latch_obj = next(o for o in interior.objects if o.object_id == latch)
        assert latch_obj.state.get("engaged") is False

    def test_door_latch_has_press_interaction(self) -> None:
        """``press`` interaction (display_label「スイッチを押す」) が定義されている。"""
        rt, _, _, vault, _, latch, _ = _setup()
        interior = rt._spot_interior_repo.find_by_spot_id(vault)
        latch_obj = next(o for o in interior.objects if o.object_id == latch)
        press = next(
            (i for i in latch_obj.interactions if i.action_name == "press"), None
        )
        assert press is not None
        assert "スイッチを押す" in press.display_label
