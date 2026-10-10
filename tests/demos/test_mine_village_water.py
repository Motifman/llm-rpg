"""廃坑の山村 (`mine_village_v1`) の水門・排水・閂・支柱が、設計の決まりどおりに働くことを保証する。

設計は docs/mine_village_scenario_design.md の「中心の仕掛け: 水門と排水」と、
決まりの一覧の R1 (水門がどこを沈めるか)、R2 (閉じても水はすぐ引かず、ポンプの
切り替え弁で選んだ場所が引く)、R3 (ポンプは燃料を使う)、R10 (支柱を倒すと二度と
通れない)、敵対の手段の「閉じ込める」(閂は掛けた側からしか外せない)。

決まりは表としてここに置き、シナリオを読み込んで操作を順に実行した結果と突き合わせる。
シナリオの値を書き換えたら、この表との食い違いで気づけるようにするため。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.application.world_graph.world_flag_state import (
    WorldFlagMutationContext,
    WorldFlagMutationSource,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
    InteractionNotFoundException,
)
from ai_rpg_world.domain.world_graph.value_object.connection_id import ConnectionId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_SCENARIO = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "mine_village_v1.json"

_HARU = PlayerId(1)
_GEN = PlayerId(3)

#: R1: 水門 → (置き場所, 沈む通路)。
_GATES = {
    "gate_a": ("north_tunnel", {"stun_sab"}),
    "gate_b": ("south_tunnel", {"nsb_ntun"}),
    "gate_c": ("mid_junction", {"junction_shortcut", "machine_shortcut", "shortcut_lift"}),
}
_FLOODABLE = set().union(*(c for _, c in _GATES.values()))

#: R2: 切り替え弁の目盛り → ポンプで水が引く水門の側。目盛りとの対応はどこにも書かない。
_VALVE = {"turn_valve_to_one": "gate_a", "turn_valve_to_two": "gate_c", "turn_valve_to_three": "gate_b"}

#: 仮の値 (設計の「未決」)。水門を閉じてから、溜まった水が自然に引くまでの tick。
_DRAIN_TICKS = 12
#: 燃料の缶 1 つで発電機にたまる量と、ポンプ 1 回で使う量。
_CAN_FUEL = 3
_PUMP_FUEL = 1


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _place(runtime, pid: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    entity = EntityId.create(int(pid))
    graph.unplace_entity(entity)
    graph.place_entity(entity, SpotId.create(runtime.id_mapper.get_int("spot", spot)))
    runtime._spot_graph_repo.save(graph)


def _act(runtime, pid: PlayerId, spot: str, obj: str, action: str):
    _place(runtime, pid, spot)
    return runtime.do_interact(pid, obj, action)


def _try(runtime, pid: PlayerId, spot: str, obj: str, action: str) -> tuple[str, str]:
    """操作を試し、(結果, 返った文) を返す。

    結果は 3 つに分ける。"done" はできた、"refused" は前提条件で断られた、
    "absent" はその操作がいま出ていない (hide_when_flag_preconditions_fail で隠れた、
    または名前の打ち間違い)。断られたことを確かめるテストは "refused" を見る。
    """
    _place(runtime, pid, spot)
    try:
        result = runtime.do_interact(pid, obj, action)
    except InteractionNotAllowedException as exc:
        return "refused", str(exc)
    except InteractionNotFoundException as exc:
        return "absent", str(exc)
    return "done", "\n".join(result.messages)


def _ticks(runtime, n: int) -> None:
    for _ in range(n):
        runtime.advance_tick()


def _passable(runtime, connection: str) -> bool:
    graph = runtime._spot_graph_repo.find_graph()
    cid = ConnectionId.create(runtime.id_mapper.get_int("connection", connection))
    return bool(graph.get_connection(cid).passage.traversable)


def _blocked(runtime) -> set[str]:
    raw = json.loads(_SCENARIO.read_text(encoding="utf-8"))
    return {c["id"] for c in raw["connections"] if not _passable(runtime, c["id"])}


def _reachable(runtime, start: str) -> set[str]:
    """いま通れる通路だけをたどって、start から行ける spot の集合。"""
    raw = json.loads(_SCENARIO.read_text(encoding="utf-8"))
    seen = {start}
    frontier = [start]
    while frontier:
        here = frontier.pop()
        for c in raw["connections"]:
            if here not in (c["from"], c["to"]) or not _passable(runtime, c["id"]):
                continue
            there = c["to"] if c["from"] == here else c["from"]
            if there not in seen:
                seen.add(there)
                frontier.append(there)
    return seen


def _fuel(runtime) -> int:
    from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId

    spot = SpotId.create(runtime.id_mapper.get_int("spot", "machine_room"))
    interior = runtime._spot_interior_repo.find_by_spot_id(spot)
    obj = interior.get_object(SpotObjectId.create(runtime.id_mapper.get_int("object", "generator")))
    return int(obj.state.get("fuel", 0))


def _open_gate(runtime, gate: str) -> None:
    _act(runtime, _HARU, _GATES[gate][0], gate, "open_gate")


def _close_gate(runtime, gate: str) -> None:
    _act(runtime, _HARU, _GATES[gate][0], gate, "close_gate")


def _fuel_and_start_generator(runtime, cans: int = 1) -> None:
    for _ in range(cans):
        _act(runtime, _HARU, "machine_room", "generator", "pour_fuel_can")
        _ticks(runtime, 1)
    _act(runtime, _HARU, "machine_room", "generator", "start_generator")




def _clear_gas(runtime) -> None:
    """掘り場のガスを抜く。ガスは確率で溜まり (R6、test_mine_village_light_gas_and_food.py)、溜まっていると予備の燃料が取れない。燃料の量を見るテストを偶然に左右させないため。"""
    if "gas_present" in runtime._world_flag_state.as_frozen_set():
        runtime._world_flag_state.remove(
            "gas_present",
            context=WorldFlagMutationContext(source=WorldFlagMutationSource.SCENARIO_EVENT, actor_player_id=None),
        )

class TestGatesFloodTheirTargets:
    """R1: 水門ごとに沈む通路が決まっていて、ほかの通路は沈まないことを保証する。"""

    def test_nothing_is_flooded_at_start(self, runtime) -> None:
        """始まった時点では、沈む通路も含めて全部の通路が通れる。"""
        _ticks(runtime, 1)

        assert _blocked(runtime) == set()

    @pytest.mark.parametrize("gate", sorted(_GATES))
    def test_opening_a_gate_floods_only_its_passages(self, runtime, gate) -> None:
        """水門を開けると、次の tick にその水門の沈める通路だけが通れなくなる (水門 A なら南の出入り口)。"""
        _open_gate(runtime, gate)
        _ticks(runtime, 1)

        assert _blocked(runtime) == _GATES[gate][1]


class TestWaterRecedesSlowly:
    """R2 の前半: 水門を閉じても溜まった水はすぐには引かず、しばらくして自然に引くことを保証する。"""

    def test_closing_the_gate_does_not_drain_at_once(self, runtime) -> None:
        """水門 A を開けて沈めてから閉じても、閉じてから 1 tick 後の南の出入り口はまだ通れない。"""
        _open_gate(runtime, "gate_a")
        _ticks(runtime, 1)
        _close_gate(runtime, "gate_a")
        _ticks(runtime, 1)

        assert not _passable(runtime, "stun_sab")

    @pytest.mark.parametrize("gate", sorted(_GATES))
    def test_water_drains_on_its_own_exactly_after_the_drain_ticks(self, runtime, gate) -> None:
        """水門を閉じてから `_DRAIN_TICKS` - 1 tick 後はまだ沈んでいて、ちょうど `_DRAIN_TICKS` tick 後に通れる。3 つの水門で同じ。"""
        target = sorted(_GATES[gate][1])[0]
        _open_gate(runtime, gate)
        _ticks(runtime, 1)
        _close_gate(runtime, gate)

        _ticks(runtime, _DRAIN_TICKS - 1)
        still_flooded = not _passable(runtime, target)
        _ticks(runtime, 1)

        assert still_flooded
        assert _passable(runtime, target)

    def test_reopening_restarts_the_count(self, runtime) -> None:
        """閉じてから途中で開け直して閉じると、引くまでの tick は最後に閉じたときから数え直す。"""
        _open_gate(runtime, "gate_a")
        _close_gate(runtime, "gate_a")
        _ticks(runtime, _DRAIN_TICKS - 2)
        _open_gate(runtime, "gate_a")
        _close_gate(runtime, "gate_a")

        _ticks(runtime, _DRAIN_TICKS - 1)

        assert not _passable(runtime, "stun_sab")

    def test_an_open_gate_never_drains_on_its_own(self, runtime) -> None:
        """水門を開けたままにすると、水が引く tick の 3 倍待っても沈んだまま。"""
        _open_gate(runtime, "gate_a")

        _ticks(runtime, _DRAIN_TICKS * 3)

        assert not _passable(runtime, "stun_sab")


class TestPumpDrainsWhatTheValveSelects:
    """R2 の後半と R3: ポンプは切り替え弁で選んだ場所だけを引かせ、発電機の燃料を使うことを保証する。"""

    @pytest.mark.parametrize("valve", sorted(_VALVE))
    def test_pump_drains_only_the_place_the_valve_selects(self, runtime, valve) -> None:
        """3 つの水門を開けて閉じたあと、弁を合わせてポンプを動かすと、弁の目盛りの側だけが次の tick に引く。"""
        for gate in _GATES:
            _open_gate(runtime, gate)
        _ticks(runtime, 1)
        for gate in _GATES:
            _close_gate(runtime, gate)
        _fuel_and_start_generator(runtime)
        _act(runtime, _HARU, "machine_room", "valve", valve)

        _act(runtime, _HARU, "machine_room", "pump", "run_pump")
        _ticks(runtime, 1)

        assert _blocked(runtime) == _FLOODABLE - _GATES[_VALVE[valve]][1]

    def test_pump_at_the_initial_valve_mark_leaves_the_shortcut_flooded(self, runtime) -> None:
        """弁に触らずに、水門 C で沈めて閉じた近道へポンプを動かしても、近道は沈んだまま。弁は一の目盛りから始まるので、近道を引かせるには弁を回すしかない。"""
        _open_gate(runtime, "gate_c")
        _ticks(runtime, 1)
        _close_gate(runtime, "gate_c")
        _fuel_and_start_generator(runtime)

        _act(runtime, _HARU, "machine_room", "pump", "run_pump")
        _ticks(runtime, 1)

        assert not _passable(runtime, "shortcut_lift")

    def test_one_pump_run_drains_once(self, runtime) -> None:
        """弁を二 (近道) にしてポンプを 1 回動かしたあとに弁を一へ回しても、一の側の水は、ポンプをもう一度動かすまで引かない。"""
        for gate in ("gate_a", "gate_c"):
            _open_gate(runtime, gate)
        _ticks(runtime, 1)
        for gate in ("gate_a", "gate_c"):
            _close_gate(runtime, gate)
        _fuel_and_start_generator(runtime)
        _act(runtime, _HARU, "machine_room", "valve", "turn_valve_to_two")
        _act(runtime, _HARU, "machine_room", "pump", "run_pump")
        _ticks(runtime, 1)

        _act(runtime, _HARU, "machine_room", "valve", "turn_valve_to_one")
        _ticks(runtime, 1)

        assert not _passable(runtime, "stun_sab")
        assert _passable(runtime, "shortcut_lift")

    def test_pumping_while_the_gate_is_open_is_wasted(self, runtime) -> None:
        """水門 C を開けたまま、弁を近道に合わせてポンプを動かすと、燃料は減るのに近道は沈んだまま。"""
        _open_gate(runtime, "gate_c")
        _fuel_and_start_generator(runtime)
        _act(runtime, _HARU, "machine_room", "valve", "turn_valve_to_two")

        _act(runtime, _HARU, "machine_room", "pump", "run_pump")
        _ticks(runtime, 1)

        assert not _passable(runtime, "shortcut_lift")
        assert _fuel(runtime) == _CAN_FUEL - _PUMP_FUEL

    def test_pumping_uses_one_unit_of_generator_fuel(self, runtime) -> None:
        """燃料の缶 1 つで発電機の燃料は 2 になり、ポンプを 1 回動かすと 1 に減る。"""
        _fuel_and_start_generator(runtime)
        before = _fuel(runtime)

        _act(runtime, _HARU, "machine_room", "pump", "run_pump")

        assert before == _CAN_FUEL
        assert _fuel(runtime) == _CAN_FUEL - _PUMP_FUEL

    def test_a_second_pump_in_the_same_tick_is_refused(self, runtime) -> None:
        """燃料が 2 以上あっても、同じ tick に続けてポンプを動かすと 2 回目は断られ、燃料は 1 だけ減る。燃料のフラグの更新が次の tick になるため。"""
        _fuel_and_start_generator(runtime)
        _act(runtime, _HARU, "machine_room", "pump", "run_pump")

        outcome, _message = _try(runtime, _GEN, "machine_room", "pump", "run_pump")

        assert outcome == "refused"
        assert _fuel(runtime) == _CAN_FUEL - _PUMP_FUEL

    def test_pump_stops_working_when_the_fuel_runs_out(self, runtime) -> None:
        """缶 1 つ分でポンプを `_CAN_FUEL` 回動かすと燃料は 0 になり、次の 1 回は動かず、燃料も減らない。"""
        _fuel_and_start_generator(runtime)
        for _ in range(_CAN_FUEL // _PUMP_FUEL):
            _act(runtime, _HARU, "machine_room", "pump", "run_pump")
            _ticks(runtime, 1)

        outcome, message = _try(runtime, _HARU, "machine_room", "pump", "run_pump")

        assert outcome == "refused"
        assert _fuel(runtime) == 0
        assert "燃料" not in message

    def test_pump_does_nothing_before_the_generator_runs(self, runtime) -> None:
        """発電機を動かす前は、燃料を入れてあってもポンプは動かない。"""
        _act(runtime, _HARU, "machine_room", "generator", "pour_fuel_can")
        _ticks(runtime, 1)

        outcome, message = _try(runtime, _HARU, "machine_room", "pump", "run_pump")

        assert outcome == "refused"
        assert _fuel(runtime) == _CAN_FUEL
        assert "発電機" not in message

    def test_generator_does_not_start_without_fuel(self, runtime) -> None:
        """燃料を入れる前に発電機を動かそうとしても回らない。"""
        outcome, _message = _try(runtime, _HARU, "machine_room", "generator", "start_generator")

        assert outcome == "refused"

    def test_pouring_a_can_uses_up_the_can(self, runtime) -> None:
        """北のハルが持って始まる燃料の缶は、発電機に注ぐと手元から無くなり、2 つ目は注げない。"""
        _act(runtime, _HARU, "machine_room", "generator", "pour_fuel_can")

        outcome, _message = _try(runtime, _HARU, "machine_room", "generator", "pour_fuel_can")

        assert outcome == "refused"
        assert _fuel(runtime) == _CAN_FUEL


class TestFuelSupply:
    """掘り場の予備の燃料の缶が 1 度しか拾えないことを保証する。燃料の合計の釣り合いは test_mine_village_capacity_and_fuel.py が見る。"""

    def test_a_crate_gives_its_can_only_once(self, runtime) -> None:
        """掘り場の缶は 1 度しか拾えない。2 度目は断られる。"""
        _clear_gas(runtime)
        _act(runtime, _HARU, "gas_chamber", "spare_fuel_crate", "take_spare_fuel_can")

        _clear_gas(runtime)
        outcome, _message = _try(runtime, _GEN, "gas_chamber", "spare_fuel_crate", "take_spare_fuel_can")

        assert outcome == "refused"


_SIDES = {"north": ("north_tunnel", _HARU), "south": ("south_tunnel", _GEN)}


class TestFireDoorBar:
    """閉じ込める: 防火扉の閂は掛けた側からしか外せず、掛かっている間は誰も扉を通れないことを保証する。"""

    @pytest.mark.parametrize("side", sorted(_SIDES))
    def test_barring_locks_the_door(self, runtime, side) -> None:
        """どちらの側で閂を掛けても、次の tick に防火扉は通れなくなる。"""
        spot, who = _SIDES[side]
        _act(runtime, who, spot, f"fire_door_bar_{side}", f"bar_fire_door_{side}")
        _ticks(runtime, 1)

        assert not _passable(runtime, "fire_door")

    @pytest.mark.parametrize(("side", "other"), [("north", "south"), ("south", "north")])
    def test_the_other_side_cannot_lift_the_bar(self, runtime, side, other) -> None:
        """片側で掛けた閂を、反対側の閂の「外す」で外そうとしても断られ、扉は通れないまま。"""
        spot, who = _SIDES[side]
        other_spot, other_who = _SIDES[other]
        _act(runtime, who, spot, f"fire_door_bar_{side}", f"bar_fire_door_{side}")

        outcome, _message = _try(runtime, other_who, other_spot, f"fire_door_bar_{other}", f"unbar_fire_door_{other}")
        _ticks(runtime, 1)

        assert outcome == "refused"
        assert not _passable(runtime, "fire_door")

    @pytest.mark.parametrize("side", sorted(_SIDES))
    def test_the_barring_side_can_lift_it_again(self, runtime, side) -> None:
        """掛けた側の閂を同じ側で外すと、次の tick に扉はまた通れる。"""
        spot, who = _SIDES[side]
        _act(runtime, who, spot, f"fire_door_bar_{side}", f"bar_fire_door_{side}")
        _ticks(runtime, 1)

        _act(runtime, who, spot, f"fire_door_bar_{side}", f"unbar_fire_door_{side}")
        _ticks(runtime, 1)

        assert _passable(runtime, "fire_door")


class TestFellingTheTimber:
    """R10: 古い支柱を倒すと、遠回りは二度と乗り場へ通じないことを保証する。"""

    def test_felled_timber_closes_the_long_way_for_good(self, runtime) -> None:
        """支柱を倒すと、支柱の下の道は次の tick に通れなくなり、水が引く tick の 3 倍待っても戻らない。"""
        _act(runtime, _GEN, "timber_passage", "old_timber", "fell_timber")
        _ticks(runtime, 1)
        right_after = _passable(runtime, "timber_lift")

        _ticks(runtime, _DRAIN_TICKS * 3)

        assert right_after is False
        assert _blocked(runtime) == {"timber_lift"}

    @pytest.mark.parametrize(
        ("felled", "shortcut_flooded", "reachable"),
        [(False, False, True), (True, False, True), (False, True, True), (True, True, False)],
    )
    def test_lift_landing_is_reachable_unless_both_ways_are_cut(
        self, runtime, felled, shortcut_flooded, reachable
    ) -> None:
        """中層の分岐から昇降機の乗り場へ、通れる通路だけで行けるかは、支柱を倒し、かつ近道が沈んだときだけ「行けない」になる。"""
        if felled:
            _act(runtime, _GEN, "timber_passage", "old_timber", "fell_timber")
        if shortcut_flooded:
            _open_gate(runtime, "gate_c")
        _ticks(runtime, 1)

        assert ("lift_landing" in _reachable(runtime, "mid_junction")) is reachable

    def test_timber_cannot_be_felled_twice(self, runtime) -> None:
        """倒れた支柱は、もう一度倒せない。"""
        _act(runtime, _GEN, "timber_passage", "old_timber", "fell_timber")

        outcome, _message = _try(runtime, _HARU, "timber_passage", "old_timber", "fell_timber")

        assert outcome == "refused"


class TestWaterSurvivesASnapshot:
    """世界の snapshot で保存して別の runtime に戻しても、水が引くまでの数えが続くことを保証する。"""

    def test_receding_water_keeps_counting_after_restore(self, runtime, tmp_path: Path) -> None:
        """水門 A を閉じて 5 tick 後に保存し、戻した世界で残りの tick を進めると、閉じてからちょうど `_DRAIN_TICKS` tick で引く。"""
        from scripts.run_scenario_experiment import _wiring_stub_from_world_runtime

        from ai_rpg_world.application.being.experiment_snapshot_session import (
            ExperimentSnapshotSession,
        )

        _open_gate(runtime, "gate_a")
        _ticks(runtime, 1)
        _close_gate(runtime, "gate_a")
        _ticks(runtime, 5)
        ExperimentSnapshotSession(
            wiring_result=_wiring_stub_from_world_runtime(runtime), snapshot_dir=tmp_path
        ).capture_world(runtime, source_scenario="mine_village_v1", world_tick=int(runtime.current_tick()))
        restored = create_world_runtime(_SCENARIO)
        ExperimentSnapshotSession(
            wiring_result=_wiring_stub_from_world_runtime(restored), snapshot_dir=tmp_path
        ).restore_world_from_dir(restored, tmp_path, current_scenario="mine_village_v1")

        _ticks(restored, _DRAIN_TICKS - 5 - 1)
        still_flooded = not _passable(restored, "stun_sab")
        _ticks(restored, 1)

        assert still_flooded
        assert _passable(restored, "stun_sab")


class _CapturingRecorder(NullTraceRecorder):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[Any] = []

    def record(self, kind: str, **kwargs: Any):
        event = super().record(kind, **kwargs)
        self.events.append(event)
        return event


class TestWaterLeavesATrace:
    """水が沈んだ・引いたことと、それを起こした人が trace から読めることを保証する。決まりを使えたかの判定に使う。"""

    def test_flood_and_recede_are_recorded_with_their_cause(self, runtime) -> None:
        """水門 A を開けると南の出入り口の水が操作したハルの名で立ち、閉じて待つと出来事として消える。"""
        recorder = _CapturingRecorder()
        runtime.set_trace_recorder(recorder)

        _open_gate(runtime, "gate_a")
        _close_gate(runtime, "gate_a")
        _ticks(runtime, _DRAIN_TICKS + 1)

        flood = [
            e.payload
            for e in recorder.events
            if e.kind == TraceEventKind.WORLD_FLAG_CHANGED and e.payload["flag_name"] == "flooded_south_entry"
        ]
        assert [(f["set"], f["source"], f["actor_player_id"]) for f in flood] == [
            (True, "spot_interaction", int(_HARU)),
            (False, "scenario_event", None),
        ]


    def test_pump_drain_is_recorded_as_an_event(self, runtime) -> None:
        """ポンプで近道の水を引かせると、沈んだことのフラグは出来事によって消えたと trace に残る。"""
        recorder = _CapturingRecorder()
        _open_gate(runtime, "gate_c")
        _close_gate(runtime, "gate_c")
        _fuel_and_start_generator(runtime)
        _act(runtime, _HARU, "machine_room", "valve", "turn_valve_to_two")
        runtime.set_trace_recorder(recorder)

        _act(runtime, _HARU, "machine_room", "pump", "run_pump")
        _ticks(runtime, 1)

        cleared = [
            e.payload["source"]
            for e in recorder.events
            if e.kind == TraceEventKind.WORLD_FLAG_CHANGED
            and e.payload["flag_name"] == "flooded_shortcut"
            and e.payload["set"] is False
        ]
        assert cleared == ["scenario_event"]


def _interactions(raw: dict[str, Any]):
    for spot in raw["spots"]:
        for obj in spot.get("interior", {}).get("objects", []):
            for interaction in obj.get("interactions", []):
                yield obj["id"], interaction


#: 操作の前提条件に使ってよい種類。ほかの種類は試す前にヒントとして出る。金庫の番号の入力は、番号そのものを出さない。
#: 籠に乗り込んだかを見る PLAYER_STATE_IS は、乗り込んだ人から操作ごと隠れるだけでヒントを出さない。
#: 籠の席の残りを見る OBJECT_STOCK_AT_LEAST は「いっぱい」と出るが、籠を見れば分かることで、隠す決まりではない。
_ALLOWED_PRECONDITIONS = frozenset(
    {"FLAG_SET", "FLAG_NOT_SET", "HAS_ITEM", "PUZZLE_INPUT_MATCH", "PLAYER_STATE_IS", "OBJECT_STOCK_AT_LEAST"}
)


class TestRulesStayOutOfThePrompt:
    """決まりがヒントとして漏れないよう、操作の前提条件をフラグと持ち物だけで書いていることを保証する。"""

    def test_preconditions_use_only_flags_and_items(self) -> None:
        """どの操作の前提条件も、フラグか持ち物か金庫の番号の入力だけを見る。時刻・天候・物の状態の条件は試す前にヒントとして出るため使わない。番号の入力は、番号そのものを出さない。"""
        raw = json.loads(_SCENARIO.read_text(encoding="utf-8"))

        used = {
            (obj, i["action_name"], c["condition_type"])
            for obj, i in _interactions(raw)
            for c in i.get("preconditions", [])
        }

        assert {u for u in used if u[2] not in _ALLOWED_PRECONDITIONS} == set()
        assert used

    def test_every_precondition_says_its_own_failure(self) -> None:
        """どの前提条件にも failure_message を書く。既定の文は決まりの中身を漏らすことがあるため。"""
        raw = json.loads(_SCENARIO.read_text(encoding="utf-8"))

        missing = [
            (obj, i["action_name"], c["condition_type"])
            for obj, i in _interactions(raw)
            for c in i.get("preconditions", [])
            if not c.get("failure_message")
        ]

        assert missing == []

    def test_valve_marks_name_no_destination(self) -> None:
        """切り替え弁の操作の名前・説明・返る文に、どこの水を引くかを書かない。"""
        raw = json.loads(_SCENARIO.read_text(encoding="utf-8"))
        places = ("北", "南", "近道", "出入り口", "下層")

        texts = [
            json.dumps(i, ensure_ascii=False)
            for obj, i in _interactions(raw)
            if obj in {"valve", "pump"}
        ]

        assert texts
        assert [t for t in texts if any(p in t for p in places)] == []


class TestPromptsUseWorldWordsForGatesAndValve:
    """水門と弁の操作が、世界に無い A・B・C の区別や設定の番号の名前でプロンプトに出ないことを保証する。"""

    def test_full_prompts_near_the_gates_and_valve_hide_internal_names(self, runtime) -> None:
        """3 つの水門の前と、灯した機械室に 1 人ずつ立たせ、水門と弁の操作が出ているプロンプトの全文 (本文とツールの定義) に `open_gate_`・`close_gate_`・`set_valve_` が出ない。3 本目の実 run では「「北の坑道の水門」に open_gate_a した」と出ていた。"""
        lamp = ItemSpecId(runtime.id_mapper.get_int("item_spec", "lamp"))
        _place(runtime, PlayerId(4), "machine_room")
        runtime.do_interact_with_item(PlayerId(4), lamp, "light_lamp")
        for pid, spot in ((_HARU, "north_tunnel"), (_GEN, "south_tunnel"), (PlayerId(2), "mid_junction")):
            _place(runtime, pid, spot)

        texts = []
        for pid in (_HARU, PlayerId(2), _GEN, PlayerId(4)):
            prompt = runtime.build_full_prompt(pid)
            texts.append("\n".join(str(m.get("content", "")) for m in prompt["messages"]) + json.dumps(prompt["tools"], ensure_ascii=False))
        full = "\n".join(texts)

        assert "open_gate" in full and "turn_valve_to_one" in full
        assert [name for name in ("open_gate_", "close_gate_", "set_valve_") if name in full] == []
