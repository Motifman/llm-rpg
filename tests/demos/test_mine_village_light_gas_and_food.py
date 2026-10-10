"""廃坑の山村 (`mine_village_v1`) の灯り・ガス・食べ物の決まりが、設計どおりに働くことを保証する。

設計は docs/mine_village_scenario_design.md の決まりの一覧の R7 (ランプの油は使うと減る。
鍛冶場でたいまつを作れる)、R6 (カナリアが鳴きやむと、掘り場にガスが溜まっている)、
R9 (井戸の水と倉庫の保存食は、取ると減り、時間で少しずつ戻る)。

決まりはプロンプトに書かない。時刻・確率は出来事の側でフラグや持ち物に変え、操作の側は
フラグと持ち物だけを条件にする。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.llm.services.world_llm_turn.escape_tools import (
    offered_tools_from_payload,
)
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    collect_owned_item_spec_ids_from_inventory,
)
from ai_rpg_world.application.world_graph.world_flag_state import (
    WorldFlagMutationContext,
    WorldFlagMutationSource,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.value_object.agent_need import NeedType
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import InteractionNotAllowedException
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring

_SCENARIO = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "mine_village_v1.json"

_HARU, _MIO, _GEN, _SAYO = (PlayerId(i) for i in range(1, 5))
_NORTH, _SOUTH = (_HARU, _MIO), (_GEN, _SAYO)

#: 仮の値 (設計の「未決」)。
_LAMP_BURN_TICKS = 16
_TORCH_BURN_TICKS = 24
_TORCHES_AT_THE_SMITHY = 2
_GAS_TICKS = 8
_WELL_WATER = 4
_WELL_REFILL_TICKS = 6
_FOOD = 3
_FOOD_REFILL_TICKS = 24
_WATER_HEAL = 8
_FOOD_HUNGER = 40
_STARVATION_DAMAGE = 1


def _raw() -> dict[str, Any]:
    return json.loads(_SCENARIO.read_text(encoding="utf-8"))


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _place(runtime, pid: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    entity = EntityId.create(int(pid))
    graph.unplace_entity(entity)
    graph.place_entity(entity, SpotId.create(runtime.id_mapper.get_int("spot", spot)))
    runtime._spot_graph_repo.save(graph)


def _ticks(runtime, n: int) -> None:
    for _ in range(n):
        runtime.advance_tick()


def _count(runtime, pid: PlayerId, item: str) -> int:
    spec = runtime.id_mapper.get_int("item_spec", item)
    inv = runtime._player_inventory_repo.find_by_id(pid)
    return sum(
        1
        for _slot, iid in inv.iter_occupied_slots()
        if int(runtime._item_repo.find_by_id(iid).item_spec.item_spec_id.value) == spec
    )


def _owns(runtime, pid: PlayerId, item: str) -> bool:
    spec = runtime.id_mapper.get_int("item_spec", item)
    owned = collect_owned_item_spec_ids_from_inventory(
        runtime._player_inventory_repo.find_by_id(pid), runtime._item_repo
    )
    return any(int(getattr(s, "value", s)) == spec for s in owned)


def _use(runtime, pid: PlayerId, item: str, action: str) -> tuple[bool, str]:
    """手元の道具の操作を試し、(できたか, 返った文) を返す。"""
    spec = ItemSpecId(runtime.id_mapper.get_int("item_spec", item))
    try:
        result = runtime.do_interact_with_item(pid, spec, action)
    except InteractionNotAllowedException as exc:
        return False, str(exc)
    return True, "\n".join(result.messages)


def _act(runtime, pid: PlayerId, spot: str, obj: str, action: str) -> tuple[bool, str]:
    """その場所の物の操作を試し、(できたか, 返った文) を返す。"""
    _place(runtime, pid, spot)
    try:
        result = runtime.do_interact(pid, obj, action)
    except InteractionNotAllowedException as exc:
        return False, str(exc)
    return True, "\n".join(result.messages)


def _hidden_in_the_dark(runtime, pid: PlayerId) -> set[str]:
    return set(runtime.build_llm_context(pid).tool_runtime_context.dark_hidden_object_names)


def _flag(runtime, name: str, on: bool) -> None:
    state = runtime._world_flag_state
    context = WorldFlagMutationContext(source=WorldFlagMutationSource.SCENARIO_EVENT, actor_player_id=None)
    if on:
        state.add(name, context=context)
    elif name in state.as_frozen_set():
        state.remove(name, context=context)


def _flags(runtime) -> frozenset[str]:
    return runtime._world_flag_state.as_frozen_set()


def _call(runtime, pid: PlayerId, tool: str, arguments: dict[str, Any]):
    wiring = _WorldLlmWiring(
        runtime=runtime,
        observation_buffer=runtime._obs_buffer,
        short_term_memory=runtime._short_term_memory,
        llm_client=object(),
    )
    return wiring._execute_tool(
        pid,
        tool,
        {**arguments, "inner_thought": "試す"},
        runtime.build_llm_context(pid).tool_runtime_context,
        offered_tools_at_prompt=offered_tools_from_payload(wiring._build_tools_payload(pid)),
    )


def _hp(runtime, pid: PlayerId) -> int:
    return int(runtime._player_status_repo.find_by_id(pid).hp.value)


def _hunger(runtime, pid: PlayerId) -> int:
    return int(runtime._player_status_repo.find_by_id(pid).needs.get(NeedType.HUNGER).value)


class TestLampOil:
    """R7: カンテラは油を足して灯すと灯りになり、灯は時間で燃え尽き、油は使うと減ることを保証する。"""

    def test_south_carries_more_oil_than_north(self, runtime) -> None:
        """北の 2 人は油を 1 本ずつ、南の 2 人は 3 本ずつ持って始まり、全員カンテラを持つ。"""
        oil = {pid: _count(runtime, pid, "lamp_oil") for pid in _NORTH + _SOUTH}

        assert oil == {_HARU: 1, _MIO: 1, _GEN: 3, _SAYO: 3}
        assert all(_owns(runtime, pid, "lamp") for pid in _NORTH + _SOUTH)

    def test_an_unlit_lamp_shows_nothing_in_the_dark(self, runtime) -> None:
        """灯す前のカンテラを持って暗い機械室に入っても、発電機は暗くて見えない。"""
        _place(runtime, _HARU, "machine_room")

        assert "発電機" in _hidden_in_the_dark(runtime, _HARU)

    def test_lighting_the_lamp_uses_one_oil_and_shows_the_room(self, runtime) -> None:
        """ゲンが油を足してカンテラを灯すと、油が 1 本減り、暗い機械室の発電機が見える。"""
        _place(runtime, _GEN, "machine_room")

        done, message = _use(runtime, _GEN, "lamp", "light_lamp")

        assert done, message
        assert _count(runtime, _GEN, "lamp_oil") == 2
        assert "発電機" not in _hidden_in_the_dark(runtime, _GEN)

    def test_no_oil_no_light(self, runtime) -> None:
        """ハルが 1 本きりの油で灯したあとは、もう一度灯そうとしても断られる。"""
        _use(runtime, _HARU, "lamp", "light_lamp")

        done, message = _use(runtime, _HARU, "lamp", "light_lamp")

        assert not done
        assert message == "カンテラに足す油が無い。"

    def test_the_flame_burns_out_and_the_room_goes_dark(self, runtime) -> None:
        """始まってすぐ灯したカンテラは、15 tick 後はまだ灯っていて、ちょうど 16 tick 後 (`_LAMP_BURN_TICKS`) に消え、機械室は暗くなる。"""
        _place(runtime, _HARU, "machine_room")
        _use(runtime, _HARU, "lamp", "light_lamp")

        _ticks(runtime, _LAMP_BURN_TICKS - 1)
        still_lit = _owns(runtime, _HARU, "lamp_flame")
        _ticks(runtime, 1)

        assert still_lit
        assert not _owns(runtime, _HARU, "lamp_flame")
        assert "発電機" in _hidden_in_the_dark(runtime, _HARU)

    def test_without_light_the_tool_refuses_to_touch_the_generator(self, runtime) -> None:
        """灯していないハルが暗い機械室で発電機を操作しようとすると、ツールが「暗くて見えない」と断り、燃料は入らない。"""
        _place(runtime, _HARU, "machine_room")

        result = _call(runtime, _HARU, "interact", {"target_label": "発電機", "action_name": "pour_fuel_can"})

        assert not result.success
        assert "暗くて見えない" in result.message
        assert _owns(runtime, _HARU, "fuel_can")

    def test_holder_hears_the_flame_burned_out_by_name(self, runtime) -> None:
        """灯したハルには、灯した tick に「カンテラの灯を入手しました。」、16 tick 目に「カンテラの灯が燃え尽きた。」が届く。品名の無い文と「捨て」の文は届かない。3 本目の実 run では「何かのアイテムを捨てました。」と届き、燃え尽きの決まりを学ぶ手がかりにならなかった。"""
        _use(runtime, _HARU, "lamp", "light_lamp")

        _ticks(runtime, _LAMP_BURN_TICKS)

        proses = [entry.output.prose for entry in runtime._obs_buffer.get_observations(_HARU)]
        assert "カンテラの灯を入手しました。" in proses
        assert "カンテラの灯が燃え尽きた。" in proses
        assert [p for p in proses if "何かのアイテム" in p or "捨て" in p] == []

    def test_lighting_tells_the_oil_left_the_hand_by_name(self, runtime) -> None:
        """油を足して灯すと、油が手もとから減ったことが品名つきで届き、「捨て」とは言わない。"""
        _use(runtime, _GEN, "lamp", "light_lamp")

        proses = [entry.output.prose for entry in runtime._obs_buffer.get_observations(_GEN)]
        assert "カンテラの油が手もとからなくなった。" in proses
        assert [p for p in proses if "捨て" in p] == []

    def test_a_stolen_flame_is_not_said_to_have_burned_out(self, runtime) -> None:
        """灯をゲンに奪われたハルには「カンテラの灯が手もとからなくなった。」が届き、「燃え尽きた」は届かない。燃え尽きの文は、出来事で取り除かれたときだけ使う。"""
        _use(runtime, _HARU, "lamp", "light_lamp")
        _place(runtime, _HARU, "village_square")
        _place(runtime, _GEN, "village_square")

        runtime.do_interact_with_player(_GEN, _HARU, "pickpocket", interaction_parameters={"item": "カンテラの灯"})

        proses = [entry.output.prose for entry in runtime._obs_buffer.get_observations(_HARU)]
        assert not _owns(runtime, _HARU, "lamp_flame")
        assert "カンテラの灯が手もとからなくなった。" in proses
        assert [p for p in proses if "燃え尽き" in p] == []

    def test_a_flame_lit_late_burns_out_at_the_same_time_as_the_rest(self, runtime) -> None:
        """灯の燃え尽きは灯した時刻から数えない。10 tick 目に灯した灯も、16 tick 目に消える。たいまつは巻き込まない。"""
        _act(runtime, _GEN, "smithy", "smithy_rags", "make_torch")
        _ticks(runtime, 10)
        _use(runtime, _GEN, "lamp", "light_lamp")

        _ticks(runtime, _LAMP_BURN_TICKS - 10)

        assert not _owns(runtime, _GEN, "lamp_flame")
        assert _owns(runtime, _GEN, "torch")

    def test_a_flame_cannot_be_set_down_to_stop_it_burning(self, runtime) -> None:
        """足もとに置く操作 (drop_item) はツールに出ない。灯とたいまつの燃え尽きは持ち物からしか取り除けないので、置いて燃え尽きを逃れる抜け道を作らないため。"""
        tools = set(runtime.build_full_prompt(_HARU)["tools"])

        assert not any("drop_item" in name for name in tools)
        assert any("give_item" in name for name in tools)

    def test_a_teammates_flame_lights_the_room_for_both(self, runtime) -> None:
        """同じ機械室で、ゲンが灯せば、灯していないサヨにも発電機が見える。油を分けて使える。"""
        _place(runtime, _GEN, "machine_room")
        _place(runtime, _SAYO, "machine_room")

        _use(runtime, _GEN, "lamp", "light_lamp")

        assert "発電機" not in _hidden_in_the_dark(runtime, _SAYO)

    def test_the_lamp_description_does_not_say_how_long_it_burns(self) -> None:
        """カンテラ・油・灯の説明に、燃える時間の長さを書かない。"""
        texts = [s["description"] for s in _raw()["item_specs"] if s["id"] in {"lamp", "lamp_oil", "lamp_flame"}]

        assert len(texts) == 3
        assert [t for t in texts if any(ch.isdigit() for ch in t) or "tick" in t] == []


class TestTorchFromTheSmithy:
    """R7: 鍛冶場の布切れと油の瓶から、たいまつを作れ、たいまつも灯りになることを保証する。"""

    def test_a_torch_lights_the_dark_room(self, runtime) -> None:
        """油の切れたハルが鍛冶場でたいまつを作って機械室に入ると、発電機が見える。"""
        _use(runtime, _HARU, "lamp", "light_lamp")
        _ticks(runtime, _LAMP_BURN_TICKS)

        done, message = _act(runtime, _HARU, "smithy", "smithy_rags", "make_torch")
        _place(runtime, _HARU, "machine_room")

        assert done, message
        assert "発電機" not in _hidden_in_the_dark(runtime, _HARU)

    def test_the_smithy_has_rags_for_two_torches(self, runtime) -> None:
        """たいまつは 2 本まで作れ、3 本目は断られる。"""
        made = [_act(runtime, _MIO, "smithy", "smithy_rags", "make_torch")[0] for _ in range(_TORCHES_AT_THE_SMITHY)]

        done, message = _act(runtime, _MIO, "smithy", "smithy_rags", "make_torch")

        assert made == [True] * _TORCHES_AT_THE_SMITHY
        assert not done
        assert "布切れ" in message

    def test_a_torch_burns_out_too(self, runtime) -> None:
        """始まってすぐ作ったたいまつは、23 tick 後はまだ燃えていて、ちょうど 24 tick 後 (`_TORCH_BURN_TICKS`) に燃え尽きる。"""
        _act(runtime, _MIO, "smithy", "smithy_rags", "make_torch")

        _ticks(runtime, _TORCH_BURN_TICKS - 1)
        still_burning = _owns(runtime, _MIO, "torch")
        _ticks(runtime, 1)

        assert still_burning
        assert not _owns(runtime, _MIO, "torch")

    def test_the_recipe_is_not_written_down(self) -> None:
        """鍛冶場と布切れの説明と、たいまつを作る操作の表示名に、「たいまつ」を書かない。試して分かる。"""
        smithy = next(s for s in _raw()["spots"] if s["id"] == "smithy")
        rags = next(o for o in smithy["interior"]["objects"] if o["id"] == "smithy_rags")
        labels = [i["display_label"] for i in rags["interactions"]]

        assert "たいまつ" not in smithy["description"] + rags["description"] + "".join(labels)


class TestGasAndTheCanary:
    """R6: 掘り場にときどきガスが溜まり、ガスのときは予備の燃料が取れず、カナリアで前兆が分かることを保証する。"""

    def test_gas_blocks_the_spare_fuel(self, runtime) -> None:
        """ガスがあるときに掘り場で予備の燃料を取ろうとすると「息が苦しい」と断られ、缶は手に入らない。"""
        _flag(runtime, "gas_present", True)

        done, message = _act(runtime, _GEN, "gas_chamber", "spare_fuel_crate", "take_spare_fuel_can")

        assert not done
        assert "息が苦しい" in message
        assert not _owns(runtime, _GEN, "fuel_can")

    def test_without_gas_the_spare_fuel_can_be_taken(self, runtime) -> None:
        """ガスが無いときは、予備の燃料の缶が取れる。"""
        _flag(runtime, "gas_present", False)

        done, message = _act(runtime, _GEN, "gas_chamber", "spare_fuel_crate", "take_spare_fuel_can")

        assert done, message
        assert _owns(runtime, _GEN, "fuel_can")

    def test_the_canary_cage_hangs_in_the_miners_rest(self, runtime) -> None:
        """坑夫の詰所の鳥籠を下ろすと、カナリアの籠が手に入り、2 度目は断られる。"""
        first, message = _act(runtime, _HARU, "miners_rest", "canary_hook", "take_canary")
        second, _ = _act(runtime, _MIO, "miners_rest", "canary_hook", "take_canary")

        assert first, message
        assert (_owns(runtime, _HARU, "canary"), second) == (True, False)

    @pytest.mark.parametrize(("gas", "expected"), [(True, "鳴きやん"), (False, "さえずって")])
    def test_the_canary_tells_whether_there_is_gas(self, runtime, gas, expected) -> None:
        """カナリアの様子を見る 2 つの操作のどちらを選んでも、ガスがあるときは「鳴きやんだ」、無いときは「さえずっている」と返る。片方は断られたときの文で返る。"""
        _act(runtime, _HARU, "miners_rest", "canary_hook", "take_canary")
        _flag(runtime, "gas_present", gas)

        results = [_use(runtime, _HARU, "canary", a) for a in ("watch_canary_a", "watch_canary_b")]

        assert [done for done, _ in results].count(True) == 1
        assert all(expected in message for _done, message in results)

    def test_the_inventory_line_looks_the_same_with_or_without_gas(self, runtime) -> None:
        """カナリアの籠の持ち物欄は、ガスの有無で 1 文字も変わらない。様子を見なくても答えが分かる経路を作らないため。"""
        _act(runtime, _HARU, "miners_rest", "canary_hook", "take_canary")

        def canary_line() -> str:
            text = runtime.build_full_prompt(_HARU)["messages"][1]["content"]
            return next(line for line in text.splitlines() if '"カナリアの籠" —' in line)

        _flag(runtime, "gas_present", False)
        without_gas = canary_line()
        _flag(runtime, "gas_present", True)
        with_gas = canary_line()

        assert without_gas == with_gas
        assert "watch_canary_a" in with_gas and "watch_canary_b" in with_gas

    def test_gas_seeps_in_now_and_then_and_clears_after_a_while(self, runtime) -> None:
        """ガスは 400 tick のうちに溜まり、溜まってから 7 tick 後はまだあり、ちょうど 8 tick 後 (`_GAS_TICKS`) に抜ける。2 度目に溜まったときも 7 tick 後はまだある。"""
        def wait_for_gas() -> bool:
            for _ in range(400):
                runtime.advance_tick()
                if "gas_present" in _flags(runtime):
                    return True
            return False

        appeared = wait_for_gas()
        _ticks(runtime, _GAS_TICKS - 1)
        still_there = "gas_present" in _flags(runtime)
        _ticks(runtime, 1)
        cleared = "gas_present" not in _flags(runtime)

        assert (appeared, still_there, cleared) == (True, True, True)
        assert wait_for_gas()
        _ticks(runtime, _GAS_TICKS - 1)
        assert "gas_present" in _flags(runtime)

    def test_once_the_gas_clears_the_spare_fuel_can_be_taken(self, runtime) -> None:
        """ガスで断られたあと、ガスが抜けてから探り直すと、予備の燃料の缶が取れる。断られても缶は無くならない。"""
        _flag(runtime, "gas_present", True)
        refused, _ = _act(runtime, _GEN, "gas_chamber", "spare_fuel_crate", "take_spare_fuel_can")
        _flag(runtime, "gas_present", False)

        done, message = _act(runtime, _GEN, "gas_chamber", "spare_fuel_crate", "take_spare_fuel_can")

        assert (refused, done) == (False, True), message
        assert _owns(runtime, _GEN, "fuel_can")

    def test_the_canary_action_names_do_not_tell_its_state(self) -> None:
        """カナリアの様子を見る 2 つの操作の名前と表示名に、鳴き声やガスを表す語を入れず、表示名は同じにする。名前から答えを読ませないため。"""
        canary = next(s for s in _raw()["item_specs"] if s["id"] == "canary")
        names = " ".join(i["action_name"] + i["display_label"] for i in canary["interactions"])

        assert [w for w in ("sing", "silent", "gas", "鳴", "さえず") if w in names] == []
        assert len({i["display_label"] for i in canary["interactions"]}) == 1

    def test_south_knows_what_a_silent_canary_means_and_north_does_not(self) -> None:
        """南の 2 人の persona には「カナリアが鳴きやむのはガスの前兆」があり、北の 2 人には無い。カナリアの文と同じ「鳴きや」の言い方にそろえる。"""
        personas = {p["id"]: p["persona_prompt"] for p in _raw()["players"]}

        canary = next(s for s in _raw()["item_specs"] if s["id"] == "canary")
        silent = next(i for i in canary["interactions"] if i["preconditions"][0]["condition_type"] == "FLAG_SET")
        stem = "鳴きや"

        assert stem in silent["effects"][0]["parameters"]["message"]
        assert all(f"カナリアが{stem}む" in personas[p] and "ガス" in personas[p] for p in ("gen", "sayo"))
        assert all("カナリア" not in personas[p] and "ガス" not in personas[p] for p in ("haru", "mio"))

    def test_nothing_in_the_world_text_names_the_gas(self) -> None:
        """場所・物・持ち物の説明と表示名に「ガス」を書かない。分かるのは、試したときの文とカナリアの様子と南の言い伝えだけ。"""
        raw = _raw()
        texts: list[str] = []
        for spot in raw["spots"]:
            texts.append(spot["description"])
            for obj in spot.get("interior", {}).get("objects", []):
                texts.append(obj["description"])
                texts.extend(i["display_label"] for i in obj.get("interactions", []))
        for spec in raw["item_specs"]:
            texts.append(spec["description"])
            texts.extend(i["display_label"] for i in spec.get("interactions", []))

        assert [t for t in texts if "ガス" in t] == []


class TestWaterAndFood:
    """R9: 井戸の水と倉庫の保存食は、取ると減り、時間で 1 つずつ戻り、空腹と体に効くことを保証する。"""

    @pytest.mark.parametrize(
        ("spot", "obj", "action", "stock", "refill"),
        [
            ("well", "well_bucket", "draw_water", _WELL_WATER, _WELL_REFILL_TICKS),
            ("storehouse", "food_box", "take_food", _FOOD, _FOOD_REFILL_TICKS),
        ],
    )
    def test_taking_runs_it_dry_and_it_comes_back_one_at_a_time(self, runtime, spot, obj, action, stock, refill) -> None:
        """在庫の数だけ取ると次は断られ、補充の間隔 - 1 tick ではまだ取れず、間隔が経つと 1 つだけ取れる。断る文は「空」と言う。"""
        taken = [_act(runtime, _GEN, spot, obj, action)[0] for _ in range(stock)]
        empty, _ = _act(runtime, _GEN, spot, obj, action)
        _ticks(runtime, refill - 1)
        too_soon, _ = _act(runtime, _GEN, spot, obj, action)
        _ticks(runtime, 1)
        one_back, _ = _act(runtime, _GEN, spot, obj, action)
        then_empty, message = _act(runtime, _GEN, spot, obj, action)

        assert taken == [True] * stock
        assert (empty, too_soon, one_back, then_empty) == (False, False, True, False)
        assert "空" in message

    def test_eating_the_preserved_food_eases_hunger(self, runtime) -> None:
        """空腹が 80 のゲンが保存食を食べると、空腹が 40 (`_FOOD_HUNGER`) 下がる。"""
        status = runtime._player_status_repo.find_by_id(_GEN)
        status.increase_need(NeedType.HUNGER, 80)
        runtime._player_status_repo.save(status)
        _act(runtime, _GEN, "storehouse", "food_box", "take_food")

        result = _call(runtime, _GEN, "use_item", {"item_label": "保存食"})

        assert result.success, result.message
        assert _hunger(runtime, _GEN) == 80 - _FOOD_HUNGER

    def test_drinking_well_water_restores_hp(self, runtime) -> None:
        """HP が 50 のゲンが井戸の水を飲むと、HP が 8 (`_WATER_HEAL`) 戻る。"""
        status = runtime._player_status_repo.find_by_id(_GEN)
        status.apply_damage(50)
        runtime._player_status_repo.save(status)
        _act(runtime, _GEN, "well", "well_bucket", "draw_water")

        result = _call(runtime, _GEN, "use_item", {"item_label": "井戸の水"})

        assert result.success, result.message
        assert _hp(runtime, _GEN) == 50 + _WATER_HEAL

    def test_starving_wears_down_hp(self, runtime) -> None:
        """空腹が限界のゲンは、1 tick ごとに HP が 1 (`_STARVATION_DAMAGE`) 減る。空腹が限界でないサヨは減らない。"""
        status = runtime._player_status_repo.find_by_id(_GEN)
        status.increase_need(NeedType.HUNGER, 100)
        runtime._player_status_repo.save(status)

        _ticks(runtime, 2)

        assert _hp(runtime, _GEN) == 100 - 2 * _STARVATION_DAMAGE
        assert _hp(runtime, _SAYO) == 100
