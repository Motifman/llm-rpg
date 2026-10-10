"""廃坑の山村 (`mine_village_v1`) で、勝ち筋の手がかりが世界の中にあり、取り返しのつかない詰みが無いことを保証する。

最初の実 run (mine_v1_001) の点検で「直さないと次の run が意味を持たない」とされた 5 件への手当て。
設計は docs/mine_village_scenario_design.md の「2 チームと、知っていること」「中心の仕掛け: 水門と排水」
「試作」の各段。決まりの中身はプロンプトに書かず、言い伝え・札・音・手応えとして世界の側に置く。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
    InteractionNotFoundException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_SCENARIO = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "mine_village_v1.json"

_HARU, _MIO, _GEN, _SAYO = (PlayerId(i) for i in range(1, 5))
_NORTH = ("haru", "mio")
_SOUTH = ("gen", "sayo")

#: 切り替え弁の目盛り → (水が引く場所の沈んだフラグ, その場所を沈める水門, 水門の置き場所)。
_VALVE = {
    "set_valve_1": ("flooded_south_entry", "gate_a", "north_tunnel"),
    "set_valve_2": ("flooded_shortcut", "gate_c", "mid_junction"),
    "set_valve_3": ("flooded_north_entry", "gate_b", "south_tunnel"),
}

#: ポンプを動かした次の tick に機械室へ届く音。水が引いた / 水門が開いていて流れ込み続ける / 引く水が無い。
_PUMP_SOUND = {
    "drained": "勢いよく吸い上げられ",
    "refilling": "流れ込む音がやまない",
    "dry": "空気を吸う音",
}

#: 倉庫の油の樽 (仮の値、設計の「未決」)。
_OIL_STOCK = 2
_OIL_REFILL_TICKS = 12
#: 北の缶 1 つで発電機にたまる燃料。
_CAN_FUEL = 3

#: 地上が夜になる tick (1 日 48 tick、tick 36 から夜)。
_NIGHT_TICK = 40


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _raw() -> dict[str, Any]:
    return json.loads(_SCENARIO.read_text(encoding="utf-8"))


def _persona(player_id: str) -> str:
    return next(p["persona_prompt"] for p in _raw()["players"] if p["id"] == player_id)


def _object(raw: dict[str, Any], spot_id: str, object_id: str) -> dict[str, Any]:
    spot = next(s for s in raw["spots"] if s["id"] == spot_id)
    return next(o for o in spot["interior"]["objects"] if o["id"] == object_id)


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


def _flags(runtime) -> frozenset[str]:
    return runtime._world_flag_state.as_frozen_set()


def _heard(runtime, pid: PlayerId) -> list[str]:
    return [
        e.output.prose
        for e in runtime._obs_buffer.get_observations(pid)
        if e.output.structured.get("type") == "scenario_event"
    ]


def _start_generator(runtime) -> None:
    _act(runtime, _HARU, "machine_room", "generator", "pour_fuel_can")
    _ticks(runtime, 1)
    _act(runtime, _HARU, "machine_room", "generator", "start_generator")
    _ticks(runtime, 1)


def _pump_with(runtime, valve: str) -> list[str]:
    """弁を合わせてポンプを動かし、次の tick に機械室のハルへ届いた音を返す。"""
    _act(runtime, _HARU, "machine_room", "valve", valve)
    before = len(_heard(runtime, _HARU))
    _act(runtime, _HARU, "machine_room", "pump", "run_pump")
    _ticks(runtime, 1)
    return _heard(runtime, _HARU)[before:]


class TestTheLiftKeyHasAClue:
    """起動鍵が要ることと鍵の在りかが、南の言い伝えと乗り場の札で分かることを保証する。"""

    @pytest.mark.parametrize("player_id", _SOUTH)
    def test_south_remembers_the_key_is_kept_in_the_office_safe(self, player_id) -> None:
        """南の 2 人は、昇降機を動かす起動鍵が事務所の金庫にしまわれていたことを覚えている。"""
        persona = _persona(player_id)

        assert re.search("起動鍵[^。]*金庫", persona)

    @pytest.mark.parametrize("player_id", _NORTH)
    def test_north_does_not_know_the_safe(self, player_id) -> None:
        """北の 2 人は、金庫も番号も知らない。鍵の在りかは乗り場の札で知る。"""
        persona = _persona(player_id)

        assert "金庫" not in persona
        assert "1907" not in persona

    def test_lift_plate_says_the_key_is_kept_at_the_office(self) -> None:
        """乗り場の昇降機の札に、起動鍵が事務所で預かられていることが刻まれている。"""
        lift = _object(_raw(), "lift_landing", "lift")

        assert re.search("起動鍵[^。]*事務所", lift["description"])


class TestTheSurveyDiaryReadsAsAStateNotASteps:
    """北の測量日誌が、水門を開けてからポンプという手順に読めない書き方であることを保証する。"""

    @pytest.mark.parametrize("player_id", _NORTH)
    def test_diary_describes_the_open_gate_as_a_state(self, player_id) -> None:
        """日誌の水門の文は「開いているあいだ」の形で状態として書き、開ける・動かす行為を促す活用形 (開けると、開ければ、動かせば、回せば など) を使わない。"""
        persona = _persona(player_id)

        gate_sentences = [s for s in persona.split("。") if "水門" in s]

        assert gate_sentences
        assert all("あいだ" in s for s in gate_sentences)
        assert re.search("開け[るれたよてば]|動かせ[ばる]|回せ[ばる]|回し[たて]", persona) is None

    @pytest.mark.parametrize("player_id", _NORTH)
    def test_gate_and_pump_are_not_in_the_same_sentence(self, player_id) -> None:
        """日誌の水門の文とポンプの文は別の文で、1 つの文の中で順番に並ばない。"""
        sentences = _persona(player_id).split("。")

        assert not any("水門" in s and "ポンプ" in s for s in sentences)


class TestThePumpSoundsDifferentlyByWhatItDrew:
    """ポンプを動かした結果が、水が引いた・流れ込み続ける・引く水が無い、で違う音として機械室に届くことを保証する。"""

    @pytest.mark.parametrize("valve", sorted(_VALVE))
    def test_pump_drains_a_flooded_place_whose_gate_is_closed(self, runtime, valve) -> None:
        """水門を閉じたあとも沈んでいる場所に弁を合わせてポンプを動かすと、水が引き、機械室に「勢いよく吸い上げられ」る音が届く。"""
        flood, gate, gate_spot = _VALVE[valve]
        _act(runtime, _HARU, gate_spot, gate, f"open_{gate}")
        _ticks(runtime, 1)
        _act(runtime, _HARU, gate_spot, gate, f"close_{gate}")
        _start_generator(runtime)
        assert flood in _flags(runtime)

        heard = _pump_with(runtime, valve)

        assert flood not in _flags(runtime)
        assert [h for h in heard if _PUMP_SOUND["drained"] in h]
        assert not [h for h in heard if _PUMP_SOUND["refilling"] in h or _PUMP_SOUND["dry"] in h]

    @pytest.mark.parametrize("valve", sorted(_VALVE))
    def test_pump_cannot_beat_an_open_gate(self, runtime, valve) -> None:
        """水門が開いたまま、その水門が沈める場所に弁を合わせてポンプを動かすと、水は引かず、機械室に「流れ込む音がやまない」が届く。"""
        flood, gate, gate_spot = _VALVE[valve]
        _act(runtime, _HARU, gate_spot, gate, f"open_{gate}")
        _start_generator(runtime)

        heard = _pump_with(runtime, valve)

        assert flood in _flags(runtime)
        assert [h for h in heard if _PUMP_SOUND["refilling"] in h]
        assert not [h for h in heard if _PUMP_SOUND["drained"] in h]

    @pytest.mark.parametrize("valve", sorted(_VALVE))
    def test_pump_on_a_dry_place_only_draws_air(self, runtime, valve) -> None:
        """どこも沈んでいないときにポンプを動かすと、どの目盛りでも、機械室に「空気を吸う音」だけが届く。"""
        _start_generator(runtime)

        heard = _pump_with(runtime, valve)

        assert [h for h in heard if _PUMP_SOUND["dry"] in h]
        assert not [h for h in heard if _PUMP_SOUND["drained"] in h or _PUMP_SOUND["refilling"] in h]

    @pytest.mark.parametrize("valve", sorted(_VALVE))
    @pytest.mark.parametrize("flooded,gate_open", [(False, False), (True, False), (True, True)])
    def test_exactly_one_sound_for_every_valve_and_water_state(self, valve, flooded, gate_open) -> None:
        """弁の目盛り・弁の先が沈んでいるか・その水門が開いているかのどの組み合わせでも、ポンプの音の出来事はちょうど 1 つだけ条件を満たす。水門が開いていれば必ず沈んでいるので、開いていて沈んでいない組は無い。"""
        flood, gate, _spot = _VALVE[valve]
        flags = {"pump_pulse", f"valve_{valve[-1]}"}
        if flooded:
            flags.add(flood)
        if gate_open:
            flags.add(f"{gate}_open")

        def holds(cond: dict[str, Any]) -> bool:
            if cond["condition_type"] == "FLAG_SET":
                return cond["flag_name"] in flags
            if cond["condition_type"] == "FLAG_NOT_SET":
                return cond["flag_name"] not in flags
            raise AssertionError(cond)

        matching = [
            e["id"]
            for e in _raw()["scenario_events"]
            if e["id"].startswith("pump_sounds_") and all(holds(c) for c in e["conditions"])
        ]

        assert len(matching) == 1

    def test_pump_sound_reaches_only_the_machine_room(self, runtime) -> None:
        """ポンプの音は機械室にいる人にだけ届き、離れた場所の人には届かない。"""
        _place(runtime, _GEN, "south_adit_end")
        _start_generator(runtime)
        before = len(_heard(runtime, _GEN))

        _pump_with(runtime, "set_valve_2")

        assert not [h for h in _heard(runtime, _GEN)[before:] if "配管" in h]

    def test_pump_sounds_name_no_place_and_no_gate(self) -> None:
        """ポンプの音の文は、場所の名前も水門も出さない。どこの水が引いたかは、行ってみて知る。"""
        raw = _raw()
        place_names = [s["name"] for s in raw["spots"]]
        texts = [
            eff["parameters"]["message"]
            for e in raw["scenario_events"]
            if e["id"].startswith("pump_sounds_")
            for eff in e["effects"]
            if eff["effect_type"] == "SHOW_MESSAGE"
        ]

        assert len(texts) == 3 * len(_VALVE)
        assert all("水門" not in t and not any(n in t for n in place_names) for t in texts)


class TestThePumpRefusesForEachReasonInItsOwnWords:
    """ポンプが動かない理由 (電気が来ていない、いま動いている最中、燃料が足りない) ごとに、違う文で断られることを保証する。"""

    def test_three_reasons_have_three_different_sentences(self) -> None:
        """ポンプの 3 つの前提条件は、どれも違う断りの文を持つ。"""
        pump = _object(_raw(), "machine_room", "pump")
        messages = [p["failure_message"] for p in pump["interactions"][0]["preconditions"]]

        assert len(messages) == 3
        assert len(set(messages)) == 3

    def test_second_person_in_the_same_tick_hears_the_pump_already_running(self, runtime) -> None:
        """同じ tick に先の 1 人がポンプを動かすと、次の人は「動いている最中」と断られ、電気が来ていないときの文にはならない。"""
        _start_generator(runtime)
        _act(runtime, _HARU, "machine_room", "pump", "run_pump")

        outcome, message = _try(runtime, _GEN, "machine_room", "pump", "run_pump")

        assert outcome == "refused"
        assert "最中" in message
        assert "ぴくりとも" not in message

    def test_pump_without_power_is_refused_with_the_still_sentence(self, runtime) -> None:
        """発電機が回っていないときは、ポンプは「ぴくりとも動かない」と断られる。"""
        outcome, message = _try(runtime, _HARU, "machine_room", "pump", "run_pump")

        assert outcome == "refused"
        assert "ぴくりとも" in message

    def test_after_the_fuel_runs_out_the_generator_stops_and_its_hum_is_heard_to_break(self, runtime) -> None:
        """缶 1 つ分を使い切るまでポンプを動かすと、次の tick に発電機が止まり、離れた場所の人にも唸りが途切れたことが名前なしで届く。そのあとのポンプは「ぴくりとも動かない」と断られる。燃料の断りの文はこの流れでは出ない (燃料が 0 になった tick のうちに発電機が止まる)。"""
        _place(runtime, _GEN, "south_adit_end")
        _start_generator(runtime)
        before = len(_heard(runtime, _GEN))
        for _ in range(_CAN_FUEL):
            _act(runtime, _HARU, "machine_room", "pump", "run_pump")
            _ticks(runtime, 1)

        outcome, message = _try(runtime, _HARU, "machine_room", "pump", "run_pump")
        broke = [h for h in _heard(runtime, _GEN)[before:] if "途切れ" in h]

        assert "generator_running" not in _flags(runtime)
        assert len(broke) == 1
        assert "ハル" not in broke[0]
        assert outcome == "refused"
        assert "ぴくりとも" in message

    def test_pump_sentences_do_not_name_the_generator_or_fuel(self) -> None:
        """断りの文は、発電機も燃料も名指ししない。ポンプが発電機の燃料で動くこと (R3) は試して学ぶ。"""
        pump = _object(_raw(), "machine_room", "pump")
        messages = [p["failure_message"] for p in pump["interactions"][0]["preconditions"]]

        assert all("発電機" not in m and "燃料" not in m for m in messages)


class TestLampOilCanBeFoundAgain:
    """灯りの油を使い切っても、倉庫の油の樽から時間をかけて補えて、取り返しのつかない詰みにならないことを保証する。"""

    def test_oil_barrel_gives_oil_until_it_is_empty(self, runtime) -> None:
        """倉庫の油の樽から `_OIL_STOCK` 本まで汲め、空になると断られる。"""
        for _ in range(_OIL_STOCK):
            outcome, _message = _try(runtime, _HARU, "storehouse", "oil_barrel", "draw_lamp_oil")
            assert outcome == "done"

        outcome, message = _try(runtime, _HARU, "storehouse", "oil_barrel", "draw_lamp_oil")

        assert outcome == "refused"
        assert message

    def test_oil_barrel_is_still_empty_one_tick_before_the_interval(self, runtime) -> None:
        """空になった油の樽は、`_OIL_REFILL_TICKS` - 1 tick たっただけでは、まだ汲めない。"""
        for _ in range(_OIL_STOCK):
            _act(runtime, _HARU, "storehouse", "oil_barrel", "draw_lamp_oil")
        _ticks(runtime, _OIL_REFILL_TICKS - 1)

        outcome, _message = _try(runtime, _HARU, "storehouse", "oil_barrel", "draw_lamp_oil")

        assert outcome == "refused"

    def test_oil_barrel_refills_one_after_the_interval(self, runtime) -> None:
        """空になった油の樽は、`_OIL_REFILL_TICKS` tick たつと 1 本ぶん汲めるようになる。"""
        for _ in range(_OIL_STOCK):
            _act(runtime, _HARU, "storehouse", "oil_barrel", "draw_lamp_oil")
        _ticks(runtime, _OIL_REFILL_TICKS)

        outcome, _message = _try(runtime, _HARU, "storehouse", "oil_barrel", "draw_lamp_oil")

        assert outcome == "done"

    def test_oil_barrel_is_visible_at_night_without_a_light(self, runtime) -> None:
        """倉庫は屋内の明るい場所で、地上が夜の tick でも暗くならず、灯りを持たない人に油の樽が見える。地下で灯りを失った人が補いに戻れるようにするため。"""
        storehouse = next(s for s in _raw()["spots"] if s["id"] == "storehouse")
        assert storehouse["is_outdoor"] is False
        assert storehouse["atmosphere"]["lighting"] == "BRIGHT"
        _ticks(runtime, _NIGHT_TICK)
        _place(runtime, _HARU, "storehouse")

        hidden = set(runtime.build_llm_context(_HARU).tool_runtime_context.dark_hidden_object_names)
        text = "\n".join(str(m.get("content", "")) for m in runtime.build_full_prompt(_HARU)["messages"])

        assert "油の樽" in text
        assert "油の樽" not in hidden

    def test_oil_barrel_says_nothing_about_burning_time(self) -> None:
        """油の樽の説明と文は、灯がいつ燃え尽きるかを書かない (R7 は試して学ぶ)。"""
        barrel = _object(_raw(), "storehouse", "oil_barrel")
        texts = [barrel["description"]] + [
            eff["parameters"]["message"]
            for it in barrel["interactions"]
            for eff in it["effects"]
            if eff["effect_type"] == "SHOW_MESSAGE"
        ]

        assert all(re.search("燃え尽き|tick|刻", t) is None for t in texts)


class TestSmallCanActionMatchesItsName:
    """発電機の給油の操作名が、倉庫の持ち物の名前とそろっていることを保証する。"""

    def test_small_can_pour_label_uses_the_item_name(self) -> None:
        """「燃料が少し残った缶」を注ぐ操作の表示名は、持ち物の名前を含む。"""
        raw = _raw()
        item_name = next(i["name"] for i in raw["item_specs"] if i["id"] == "small_fuel_can")
        generator = _object(raw, "machine_room", "generator")
        label = next(i["display_label"] for i in generator["interactions"] if i["action_name"] == "pour_small_fuel_can")

        assert item_name in label
