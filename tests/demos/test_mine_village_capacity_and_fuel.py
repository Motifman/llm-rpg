"""廃坑の山村 (`mine_village_v1`) で、籠の定員が早くから分かることと、燃料の量で昇降機とポンプの釣り合いが取れていることを保証する。

設計は docs/mine_village_scenario_design.md の「籠の定員の知らせ方」と「勝つまでの道」の燃料の段。
最初の実 run (mine_v1_001) で、4 人が出会っても取り合う相手だと分からず 1 つのグループとして動いたこと、
ポンプ 2 回で燃料が尽きて行き詰まったことへの手当て。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.world_graph.world_flag_state import (
    WorldFlagMutationContext,
    WorldFlagMutationSource,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
    InteractionNotFoundException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.domain.world_graph.value_object.spot_object_id import SpotObjectId

_SCENARIO = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "mine_village_v1.json"

_HARU = PlayerId(1)

#: 籠の定員。札の文、人格の言い伝え、籠の席の数がこの値でそろう。
_LIFT_CAPACITY = 3
_CAPACITY_WORD = "三人"

#: 燃料の釣り合い (設計の「未決」)。缶 1 つで発電機にたまる量、残りの少ない缶の量、
#: ポンプ 1 回で使う量、昇降機を動かすのに要る量。
_CAN_FUEL = 3
_SMALL_CAN_FUEL = 1
_PUMP_FUEL = 1
_LIFT_FUEL = 2
_TOTAL_FUEL = _CAN_FUEL * 2 + _SMALL_CAN_FUEL
_WARM_TICKS = 6
_SAFE_CODE = "1907"


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _raw() -> dict[str, Any]:
    return json.loads(_SCENARIO.read_text(encoding="utf-8"))


def _object(raw: dict[str, Any], spot_id: str, object_id: str) -> dict[str, Any]:
    spot = next(s for s in raw["spots"] if s["id"] == spot_id)
    return next(o for o in spot["interior"]["objects"] if o["id"] == object_id)


def _place(runtime, pid: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    entity = EntityId.create(int(pid))
    graph.unplace_entity(entity)
    graph.place_entity(entity, SpotId.create(runtime.id_mapper.get_int("spot", spot)))
    runtime._spot_graph_repo.save(graph)


def _act(runtime, pid: PlayerId, spot: str, obj: str, action: str, **params: str):
    _place(runtime, pid, spot)
    return runtime.do_interact(pid, obj, action, interaction_parameters=params or None)


def _try(runtime, pid: PlayerId, spot: str, obj: str, action: str) -> tuple[str, str]:
    """操作を試し、("done" / "refused" / "absent", 返った文) を返す。"""
    try:
        result = _act(runtime, pid, spot, obj, action)
    except InteractionNotAllowedException as exc:
        return "refused", str(exc)
    except InteractionNotFoundException as exc:
        return "absent", str(exc)
    return "done", "\n".join(result.messages)


def _ticks(runtime, n: int) -> None:
    for _ in range(n):
        runtime.advance_tick()


def _fuel(runtime) -> int:
    spot = SpotId.create(runtime.id_mapper.get_int("spot", "machine_room"))
    interior = runtime._spot_interior_repo.find_by_spot_id(spot)
    obj = interior.get_object(SpotObjectId.create(runtime.id_mapper.get_int("object", "generator")))
    return int(obj.state.get("fuel", 0))


def _clear_gas(runtime) -> None:
    """掘り場のガスを抜く。ガスは確率で溜まり、溜まっていると予備の燃料が取れないので、燃料の量を見るテストを偶然に左右させない。"""
    if "gas_present" in runtime._world_flag_state.as_frozen_set():
        runtime._world_flag_state.remove(
            "gas_present",
            context=WorldFlagMutationContext(source=WorldFlagMutationSource.SCENARIO_EVENT, actor_player_id=None),
        )


def _ready_lift_with_one_can(runtime) -> None:
    """鍵を取り、北の缶 1 つだけを注いで発電機を動かし、籠に乗り込む。"""
    _act(runtime, _HARU, "company_office", "office_safe", "open_safe", code=_SAFE_CODE)
    _act(runtime, _HARU, "machine_room", "generator", "pour_fuel_can")
    _ticks(runtime, 1)
    _act(runtime, _HARU, "machine_room", "generator", "start_generator")
    _act(runtime, _HARU, "lift_landing", "lift", "board_lift")


def _pump(runtime, times: int) -> None:
    for _ in range(times):
        _act(runtime, _HARU, "machine_room", "pump", "run_pump")
        _ticks(runtime, 1)


class TestLiftCapacityIsKnownEarly:
    """籠が 3 人しか乗れないことを、昇降機に着く前から全員が知り、乗り場の札でも確かめられることを保証する。"""

    def test_every_persona_says_the_cage_takes_three_and_runs_once(self) -> None:
        """4 人の人格の設定すべてに、籠には三人しか乗れないことと、一度しか動かないことが言い伝えとして書いてある。"""
        for player in _raw()["players"]:
            persona = player["persona_prompt"]
            assert f"{_CAPACITY_WORD}しか乗れない" in persona, player["id"]
            assert "一度" in persona, player["id"]

    def test_cage_plate_shows_the_same_capacity_as_the_seats(self) -> None:
        """乗り場の昇降機の説明に定員の札があり、その数が籠の席の数 (備蓄の上限) と一致する。"""
        lift = _object(_raw(), "lift_landing", "lift")

        assert "定員三名" in lift["description"]
        assert lift["state"]["stock_capacity"] == _LIFT_CAPACITY
        assert lift["state"]["stock"] == _LIFT_CAPACITY

    def test_capacity_lore_names_no_one_and_no_other_group(self) -> None:
        """定員の言い伝えは、人の名前も、別の一団がいることも含まない。相手の存在を伏せたまま、出会ったときに数で分かるようにするため。"""
        raw = _raw()
        names = [p["name"] for p in raw["players"]]
        for player in raw["players"]:
            sentence = next(s for s in player["persona_prompt"].split("。") if _CAPACITY_WORD in s)
            assert [n for n in names if n in sentence] == [], player["id"]
            assert "ほか" not in sentence and "別の" not in sentence, player["id"]

    def test_two_pairs_together_exceed_the_capacity(self) -> None:
        """どちらのチームも 2 人なので、自分たちだけなら乗れるが、もう 2 人と出会えば 4 人になり、定員を超える。"""
        raw = _raw()
        sizes = [
            sum(1 for p in raw["players"] if p["initial_state"]["team"] == t["member_state"]["team"])
            for t in raw["teams"]
        ]

        assert sizes == [2, 2]
        assert all(size <= _LIFT_CAPACITY for size in sizes)
        assert sum(sizes) > _LIFT_CAPACITY


class TestFuelBalance:
    """燃料の量で、昇降機を動かす分とポンプに回せる分が釣り合い、使いすぎると昇降機が動かなくなることを保証する。"""

    def test_all_cans_together_fill_the_generator_to_the_total(self, runtime) -> None:
        """北の缶、掘り場の缶、倉庫の残りの少ない缶をすべて注ぐと、発電機の燃料は合計 `_TOTAL_FUEL` になる。"""
        _clear_gas(runtime)
        _act(runtime, _HARU, "gas_chamber", "spare_fuel_crate", "take_spare_fuel_can")
        _act(runtime, _HARU, "storehouse", "storehouse_crates", "take_small_fuel_can")

        for action in ("pour_fuel_can", "pour_fuel_can", "pour_small_fuel_can"):
            _act(runtime, _HARU, "machine_room", "generator", action)

        assert _fuel(runtime) == _TOTAL_FUEL

    def test_one_can_leaves_room_for_one_pump_and_still_starts_the_lift(self, runtime) -> None:
        """北の缶 1 つだけでも、ポンプを 1 回動かしたあと、温まれば昇降機は動く。"""
        _ready_lift_with_one_can(runtime)
        _pump(runtime, (_CAN_FUEL - _LIFT_FUEL) // _PUMP_FUEL)
        _ticks(runtime, _WARM_TICKS)

        outcome, _message = _try(runtime, _HARU, "lift_landing", "lift", "start_lift")

        assert outcome == "done"

    def test_pumping_twice_on_one_can_leaves_too_little_for_the_lift(self, runtime) -> None:
        """北の缶 1 つでポンプを 2 回動かすと、燃料が昇降機に要る量を下回り、温まっていても昇降機は動かない。"""
        _ready_lift_with_one_can(runtime)
        _pump(runtime, 2)
        _ticks(runtime, _WARM_TICKS)

        outcome, _message = _try(runtime, _HARU, "lift_landing", "lift", "start_lift")

        assert _fuel(runtime) < _LIFT_FUEL
        assert outcome == "refused"

    def test_generator_gauge_has_a_reading_for_every_reachable_amount(self) -> None:
        """発電機の燃料計は、0 から合計 `_TOTAL_FUEL` までのどの量にも読み方の文がある。"""
        generator = _object(_raw(), "machine_room", "generator")

        readings = {d["value"] for d in generator["state_display"] if d["key"] == "fuel"}

        assert set(range(_TOTAL_FUEL + 1)) <= readings


class TestFuelLedgerPointsToTheSpareCans:
    """機械室の給油の帳面を読めば、予備の燃料のありかが分かり、量の決まりは分からないことを保証する。"""

    def test_ledger_names_where_the_spare_cans_are(self, runtime) -> None:
        """帳面をめくると、予備の缶がある掘り場と、使いかけの缶がある倉庫の名前が返る。"""
        outcome, message = _try(runtime, _HARU, "machine_room", "fuel_ledger", "read_fuel_ledger")

        assert outcome == "done"
        assert "掘り場" in message
        assert "倉庫" in message

    def test_ledger_places_match_where_the_cans_really_are(self) -> None:
        """帳面に書かれた場所と、実際に燃料の缶を出す木箱のある場所が一致する。"""
        raw = _raw()
        spot_names = {s["id"]: s["name"] for s in raw["spots"]}
        crates = {
            spot["id"]
            for spot in raw["spots"]
            for obj in spot.get("interior", {}).get("objects", [])
            for it in obj.get("interactions", [])
            for eff in it.get("effects", [])
            if eff.get("effect_type") == "GIVE_ITEM"
            and eff.get("parameters", {}).get("item_spec") in ("fuel_can", "small_fuel_can")
        }
        ledger = _object(raw, "machine_room", "fuel_ledger")
        text = ledger["interactions"][0]["effects"][0]["parameters"]["message"]

        assert crates == {"gas_chamber", "storehouse"}
        assert all(spot_names[c] in text for c in crates)

    def test_ledger_tells_neither_the_lift_fuel_nor_the_pump_cost(self, runtime) -> None:
        """帳面は、昇降機に要る燃料の量も、ポンプが燃料を使うこと (R3) も書かない。どちらも燃料計と昇降機の手応えから試して学ぶ。"""
        _outcome, message = _try(runtime, _HARU, "machine_room", "fuel_ledger", "read_fuel_ledger")

        assert re.search("目盛り|昇降機|ポンプ|[0-9一二三四五六七]つ分", message) is None

    def test_ledger_does_not_mention_the_gas(self, runtime) -> None:
        """帳面は掘り場のガスに触れない。ガスはカナリアで知る決まり (R6) なので。"""
        _outcome, message = _try(runtime, _HARU, "machine_room", "fuel_ledger", "read_fuel_ledger")

        assert re.search("ガス|息", message) is None
