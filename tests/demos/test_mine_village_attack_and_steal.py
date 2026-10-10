"""廃坑の山村 (`mine_village_v1`) の人への攻撃と奪う操作、昇降機の籠に乗り込むことが、設計どおりに働くことを保証する。

設計は docs/mine_village_scenario_design.md の「敵対の手段」の攻撃と奪う。
攻撃は 1 回のダメージが小さく、続けて殴れない。音が出て、その区画の獣を呼ぶ。
倒れた人は動けず、籠に乗り込めないので昇降機で脱出できない。仲間が手当てすれば起き上がる。
奪う操作は、明るい場所では誰がやったか見られ、暗い場所では見られにくい。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.common.exceptions import ApplicationException
from ai_rpg_world.application.llm.services.world_llm_turn.escape_tools import (
    offered_tools_from_payload,
)
from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
    collect_owned_item_spec_ids_from_inventory,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.item.value_object.item_spec_id import ItemSpecId
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import InteractionNotAllowedException
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId
from ai_rpg_world.presentation.spot_graph_game.runtime_manager import _WorldLlmWiring

_SCENARIO = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "mine_village_v1.json"

_HARU, _MIO, _GEN, _SAYO = (PlayerId(i) for i in range(1, 5))
_NAMES = {_HARU: "ハル", _MIO: "ミオ", _GEN: "ゲン", _SAYO: "サヨ"}

#: 仮の値 (設計の「未決」)。
_DAMAGE = 10
_STRIKE_COOLDOWN = 3
_STEAL_COOLDOWN = 3
_MAX_HP = 100
_LIFT_SEATS = 3
_WARM_TICKS = 6

#: 操作が断られたときに上がる例外。これ以外の例外 (配線の誤りなど) はテストを落とす。
_REFUSED = (ApplicationException, InteractionNotAllowedException)

#: 区画 → (区画の中の場所, 音を数える見えない物)。
_SECTORS = {
    "north": ("miners_rest", "noise_north_tracker"),
    "south": ("tool_store", "noise_south_tracker"),
    "deep": ("timber_passage", "noise_deep_tracker"),
}


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


def _hp(runtime, pid: PlayerId) -> int:
    return int(runtime._player_status_repo.find_by_id(pid).hp.value)


def _is_down(runtime, pid: PlayerId) -> bool:
    return not runtime._player_status_repo.find_by_id(pid).can_act()


def _try_on(runtime, actor: PlayerId, target: PlayerId, action: str, **params: str) -> tuple[bool, str]:
    """人を対象にした操作を試し、(できたか, 返った文) を返す。"""
    try:
        result = runtime.do_interact_with_player(
            actor, target, action, interaction_parameters=params or None
        )
    except _REFUSED as exc:
        return False, str(exc)
    return True, "\n".join(getattr(result, "messages", ()) or ())


def _strike(runtime, actor: PlayerId, target: PlayerId) -> tuple[bool, str]:
    return _try_on(runtime, actor, target, "strike")


def _owns(runtime, pid: PlayerId, item: str) -> bool:
    spec = runtime.id_mapper.get_int("item_spec", item)
    owned = collect_owned_item_spec_ids_from_inventory(
        runtime._player_inventory_repo.find_by_id(pid), runtime._item_repo
    )
    return any(int(getattr(s, "value", s)) == spec for s in owned)


def _slots(runtime, pid: PlayerId) -> list[tuple[int, str]]:
    """持ち物の (スロット番号, 品の文字列 ID) の並び。"""
    inv = runtime._player_inventory_repo.find_by_id(pid)
    return [
        (int(slot.value), runtime.id_mapper.get_str("item_spec", runtime._item_repo.find_by_id(iid).item_spec.item_spec_id.value))
        for slot, iid in inv.iter_occupied_slots()
    ]


def _drop(runtime, pid: PlayerId, *items: str) -> None:
    """指定した品を足もとに置く。品を指定しなければ全部置く。暗い場所を作るために、灯りを手放させる。"""
    for slot, item in _slots(runtime, pid):
        if not items or item in items:
            runtime.do_drop_item(pid, slot)


def _knock_down(runtime, actor: PlayerId, target: PlayerId) -> None:
    """間隔を空けながら、相手が倒れるまで殴る。"""
    for _ in range(_MAX_HP // _DAMAGE):
        done, message = _strike(runtime, actor, target)
        assert done, message
        _ticks(runtime, _STRIKE_COOLDOWN)
    assert _is_down(runtime, target)


def _prose(runtime, pid: PlayerId) -> list[str]:
    return [e.output.prose for e in runtime._obs_buffer.get_observations(pid)]


#: 音を数える見えない物 → 置いてある場所。
_TRACKER_SPOTS = {
    "noise_north_tracker": "north_tunnel",
    "noise_south_tracker": "south_tunnel",
    "noise_deep_tracker": "mid_junction",
}


def _noise(runtime, tracker: str) -> int:
    spot = SpotId.create(runtime.id_mapper.get_int("spot", _TRACKER_SPOTS[tracker]))
    obj_id = runtime.id_mapper.get_int("object", tracker)
    interior = runtime._spot_interior_repo.find_by_spot_id(spot)
    obj = next(o for o in interior.objects if int(o.object_id.value) == obj_id)
    return int(obj.state.get("noise", 0))


def _outcome(runtime, pid: PlayerId):
    return runtime._player_outcome_registry.get_outcome(pid)


class TestStrikingSomeone:
    """R: 人への攻撃は 1 回のダメージが小さく、続けて殴れないことを保証する。"""

    def test_one_strike_takes_ten_hp(self, runtime) -> None:
        """同じ場所にいるゲンをハルが 1 回殴ると、ゲンの HP がちょうど 10 減る。"""
        _place(runtime, _HARU, "village_square")
        _place(runtime, _GEN, "village_square")
        before = _hp(runtime, _GEN)

        done, message = _strike(runtime, _HARU, _GEN)

        assert done, message
        assert before - _hp(runtime, _GEN) == _DAMAGE

    def test_a_second_strike_needs_a_pause(self, runtime) -> None:
        """殴った直後と間隔 - 1 tick 後は断られ、間隔の tick が経つと殴れる。断られた文に tick の数は出ない。"""
        _place(runtime, _HARU, "village_square")
        _place(runtime, _GEN, "village_square")
        _strike(runtime, _HARU, _GEN)

        right_after, message = _strike(runtime, _HARU, _GEN)
        _ticks(runtime, _STRIKE_COOLDOWN - 1)
        still_too_soon, _ = _strike(runtime, _HARU, _GEN)
        _ticks(runtime, 1)
        after_the_pause, _ = _strike(runtime, _HARU, _GEN)

        assert (right_after, still_too_soon, after_the_pause) == (False, False, True)
        assert "tick" not in message

    def test_ten_strikes_knock_someone_down(self, runtime) -> None:
        """HP 100 の相手は 9 回殴られても立っていて、10 回目で倒れる。"""
        _place(runtime, _HARU, "village_square")
        _place(runtime, _GEN, "village_square")
        for _ in range(_MAX_HP // _DAMAGE - 1):
            _strike(runtime, _HARU, _GEN)
            _ticks(runtime, _STRIKE_COOLDOWN)
        standing = not _is_down(runtime, _GEN)

        _strike(runtime, _HARU, _GEN)

        assert standing
        assert _is_down(runtime, _GEN)

    def test_someone_elsewhere_cannot_be_struck(self, runtime) -> None:
        """別の場所にいる相手は殴れず、HP も減らない。"""
        _place(runtime, _HARU, "village_square")
        _place(runtime, _GEN, "smithy")

        done, message = _strike(runtime, _HARU, _GEN)

        assert not done
        assert "同じ場所" in message
        assert _hp(runtime, _GEN) == _MAX_HP

    def test_someone_already_down_cannot_be_struck_again(self, runtime) -> None:
        """倒れている相手は、もう殴れない。"""
        _place(runtime, _HARU, "village_square")
        _place(runtime, _GEN, "village_square")
        _knock_down(runtime, _HARU, _GEN)
        _ticks(runtime, _STRIKE_COOLDOWN)

        done, message = _strike(runtime, _HARU, _GEN)

        assert not done
        assert "倒れて" in message


class TestStrikingIsLoud:
    """攻撃は大きな音を立てる操作で、坑道の区画なら、その区画の音が 1 つ積もることを保証する。"""

    @pytest.mark.parametrize("sector", sorted(_SECTORS))
    def test_a_strike_in_the_mine_adds_noise_to_that_sector_only(self, runtime, sector) -> None:
        """区画の中で 1 回殴ると、その区画の音だけが 1 つ増え、ほかの区画の音は 0 のまま。1 回の攻撃の音は、何 tick 経っても 1 つのまま。"""
        spot, tracker = _SECTORS[sector]
        _place(runtime, _HARU, spot)
        _place(runtime, _GEN, spot)

        _strike(runtime, _HARU, _GEN)
        _ticks(runtime, 2)

        noise = {s: _noise(runtime, t) for s, (_, t) in _SECTORS.items()}
        assert noise == {s: (1 if s == sector else 0) for s in _SECTORS}

    def test_someone_standing_alone_in_another_sector_does_not_carry_the_noise(self, runtime) -> None:
        """深いところで殴っている間、北の詰所に 1 人で立っているミオがいても、北の区画の音は増えない。"""
        _place(runtime, _HARU, "timber_passage")
        _place(runtime, _GEN, "timber_passage")
        _place(runtime, _MIO, "miners_rest")

        _strike(runtime, _HARU, _GEN)
        _ticks(runtime, 1)

        assert (_noise(runtime, "noise_north_tracker"), _noise(runtime, "noise_deep_tracker")) == (0, 1)

    def test_two_standing_together_elsewhere_also_hear_it(self, runtime) -> None:
        """代えの限界: 深いところで殴ると、北の詰所に 2 人並んでいるミオとサヨの区画にも音が積もる。

        エンジンは、人を対象にした操作の効果から殴った場所を参照できない。区画の中に
        2 人以上いることで殴った区画を見分けているため、別の区画の 2 人組も拾う
        (docs/mine_village_scenario_design.md の「攻撃の音」)。
        """
        _place(runtime, _HARU, "timber_passage")
        _place(runtime, _GEN, "timber_passage")
        _place(runtime, _MIO, "miners_rest")
        _place(runtime, _SAYO, "miners_rest")

        _strike(runtime, _HARU, _GEN)
        _ticks(runtime, 1)

        assert (_noise(runtime, "noise_north_tracker"), _noise(runtime, "noise_deep_tracker")) == (1, 1)

    def test_a_strike_in_the_village_makes_no_mine_noise(self, runtime) -> None:
        """坑道に誰もいないとき、地上の村で殴っても、どの区画の音も増えない。"""
        _place(runtime, _HARU, "village_square")
        _place(runtime, _GEN, "village_square")

        _strike(runtime, _HARU, _GEN)
        _ticks(runtime, 1)

        assert [_noise(runtime, t) for _, t in _SECTORS.values()] == [0, 0, 0]

    def test_no_strike_no_noise_even_when_two_stand_together(self, runtime) -> None:
        """殴らなければ、坑道に 2 人で並んでいても音は積もらない。"""
        _place(runtime, _HARU, "miners_rest")
        _place(runtime, _GEN, "miners_rest")

        _ticks(runtime, 3)

        assert _noise(runtime, "noise_north_tracker") == 0


class _CapturingRecorder(NullTraceRecorder):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[Any] = []

    def record(self, kind: str, **kwargs: Any):
        event = super().record(kind, **kwargs)
        self.events.append(event)
        return event


class TestStrikingLeavesATrace:
    """攻撃した人と、音が積もった区画が trace から読めることを保証する。獣をけしかけたかの判定に使う。"""

    def test_who_struck_and_which_sector_heard_it_are_recorded(self, runtime) -> None:
        """北の詰所でハルが殴ると、音のフラグがハルの名で立ち、北の区画の音のフラグが出来事として立つ。"""
        _place(runtime, _HARU, "miners_rest")
        _place(runtime, _GEN, "miners_rest")
        recorder = _CapturingRecorder()
        runtime.set_trace_recorder(recorder)

        _strike(runtime, _HARU, _GEN)
        _ticks(runtime, 1)

        raised = [
            (e.payload["flag_name"], e.payload["source"], e.payload["actor_player_id"])
            for e in recorder.events
            if e.kind == TraceEventKind.WORLD_FLAG_CHANGED and e.payload["set"]
        ]
        assert raised == [
            ("scuffle_noise", "player_interaction", int(_HARU)),
            ("noise_north", "scenario_event", None),
        ]


class TestTendingTheDowned:
    """倒れた人は動けず、仲間が手当てすれば起き上がれることを保証する。"""

    def _tend(self, runtime, actor: PlayerId, target: PlayerId):
        wiring = _WorldLlmWiring(
            runtime=runtime,
            observation_buffer=runtime._obs_buffer,
            short_term_memory=runtime._short_term_memory,
            llm_client=object(),
        )
        return wiring._execute_tool(
            actor,
            "tend_to_player",
            {"target_player_label": _NAMES[target], "inner_thought": "起こす"},
            runtime.build_llm_context(actor).tool_runtime_context,
            offered_tools_at_prompt=offered_tools_from_payload(wiring._build_tools_payload(actor)),
        )

    def test_a_teammate_can_bring_them_back(self, runtime) -> None:
        """倒れたゲンを、同じ場所のサヨが手当てすると、ゲンは起き上がって動けるようになる。"""
        _place(runtime, _HARU, "village_square")
        _place(runtime, _GEN, "village_square")
        _place(runtime, _SAYO, "village_square")
        _knock_down(runtime, _HARU, _GEN)

        result = self._tend(runtime, _SAYO, _GEN)

        assert result.success, result.message
        assert not _is_down(runtime, _GEN)
        assert _hp(runtime, _GEN) > 0

    def test_being_down_is_not_death(self, runtime) -> None:
        """倒れた直後の人の結果は、まだ決まっていない (死ではない)。"""
        _place(runtime, _HARU, "village_square")
        _place(runtime, _GEN, "village_square")
        _knock_down(runtime, _HARU, _GEN)

        assert _outcome(runtime, _GEN) == PlayerOutcomeEnum.UNRESOLVED


def _ready_the_lift(runtime) -> None:
    """ハルが鍵と温まった発電機をそろえる。"""
    runtime.do_interact(_place_and(runtime, _HARU, "company_office"), "office_safe", "open_safe",
                        interaction_parameters={"code": "1907"})
    runtime.do_interact(_place_and(runtime, _HARU, "machine_room"), "generator", "pour_fuel_can")
    _ticks(runtime, 1)
    runtime.do_interact(_place_and(runtime, _HARU, "machine_room"), "generator", "start_generator")
    _ticks(runtime, _WARM_TICKS + 1)


def _place_and(runtime, pid: PlayerId, spot: str) -> PlayerId:
    _place(runtime, pid, spot)
    return pid


def _board(runtime, pid: PlayerId) -> tuple[bool, str]:
    _place(runtime, pid, "lift_landing")
    try:
        result = runtime.do_interact(pid, "lift", "board_lift")
    except InteractionNotAllowedException as exc:
        return False, str(exc)
    return True, "\n".join(result.messages)


def _depart(runtime) -> None:
    runtime.do_interact(_place_and(runtime, _HARU, "lift_landing"), "lift", "start_lift")
    _ticks(runtime, 1)


class TestBoardingTheLift:
    """昇降機で脱出できるのは籠に乗り込んだ人だけで、籠は 3 人で一杯になり、倒れた人は乗り込めないことを保証する。"""

    def test_only_those_aboard_escape(self, runtime) -> None:
        """籠に乗り込んだハルとゲンは脱出し、乗り場に立っているだけのミオは取り残される。"""
        _ready_the_lift(runtime)
        _board(runtime, _HARU)
        _board(runtime, _GEN)
        _place(runtime, _MIO, "lift_landing")

        _depart(runtime)

        assert _outcome(runtime, _HARU) == PlayerOutcomeEnum.RESCUED
        assert _outcome(runtime, _GEN) == PlayerOutcomeEnum.RESCUED
        assert _outcome(runtime, _MIO) == PlayerOutcomeEnum.STRANDED

    def test_the_cage_is_full_with_three(self, runtime) -> None:
        """3 人が乗り込むと、4 人目は「いっぱい」と断られる。"""
        for pid in (_HARU, _MIO, _GEN):
            assert _board(runtime, pid)[0]

        done, message = _board(runtime, _SAYO)

        assert not done
        assert "いっぱい" in message

    def test_boarding_twice_does_not_take_a_second_seat(self, runtime) -> None:
        """乗り込んだ人がもう一度乗り込もうとしても断られ、残りの 2 人はまだ乗り込める。"""
        _board(runtime, _HARU)

        again, message = _board(runtime, _HARU)

        assert not again
        assert message == "もう籠の中にいる。"
        assert [_board(runtime, p)[0] for p in (_MIO, _GEN)] == [True, True]

    def test_the_lift_cannot_be_started_from_outside_the_cage(self, runtime) -> None:
        """準備がそろっていても、籠に乗り込んでいないハルには昇降機を動かせない。"""
        _ready_the_lift(runtime)
        _place(runtime, _HARU, "lift_landing")

        with pytest.raises(InteractionNotAllowedException, match="乗り込まないと"):
            runtime.do_interact(_HARU, "lift", "start_lift")

        assert "lift_departed" not in runtime._world_flag_state.as_frozen_set()

    def test_leaving_the_cage_frees_the_seat(self, runtime) -> None:
        """3 人で一杯の籠からハルが降りると、籠の中の場所を手放し、サヨが乗り込める。降りたハルからは物を奪える。"""
        for pid in (_HARU, _MIO, _GEN):
            _board(runtime, pid)
        berth = runtime.id_mapper.get_int("item_spec", "lift_berth")

        runtime.do_interact_with_item(_HARU, ItemSpecId(berth), "leave_lift")

        assert not _owns(runtime, _HARU, "lift_berth")
        assert _board(runtime, _SAYO)[0]
        assert _try_on(runtime, _GEN, _HARU, "pickpocket", item="燃料の缶")[0]

    def test_a_seat_left_outside_the_landing_does_not_escape(self, runtime) -> None:
        """籠に乗り込んでから乗り場を離れたミオは、籠の中の場所を持っていても、籠が上がると取り残される。"""
        _ready_the_lift(runtime)
        _board(runtime, _HARU)
        _board(runtime, _MIO)
        _place(runtime, _MIO, "machine_room")

        _depart(runtime)

        assert _outcome(runtime, _MIO) == PlayerOutcomeEnum.STRANDED

    def test_the_downed_get_no_turn_and_are_left_behind(self, runtime) -> None:
        """乗り場で倒れたゲンには手番が回らない。籠に乗り込む手番が無いので、乗り場にいても籠が上がると取り残される。"""
        _ready_the_lift(runtime)
        _board(runtime, _HARU)
        _place(runtime, _MIO, "lift_landing")
        _place(runtime, _GEN, "lift_landing")
        _knock_down(runtime, _MIO, _GEN)

        gets_a_turn = runtime._player_life_query.can_take_turn(_GEN)
        _depart(runtime)

        assert not gets_a_turn
        assert _outcome(runtime, _GEN) == PlayerOutcomeEnum.STRANDED


class TestTakingThings:
    """人から物を奪えることと、明るさで見られ方が変わることを保証する。"""

    def test_take_a_named_item_from_someone_standing(self, runtime) -> None:
        """同じ場所に立っているハルから、ゲンが燃料の缶を名指しで奪うと、缶はゲンの持ち物に移る。"""
        _place(runtime, _HARU, "village_square")
        _place(runtime, _GEN, "village_square")

        done, message = _try_on(runtime, _GEN, _HARU, "pickpocket", item="燃料の缶")

        assert done, message
        assert not _owns(runtime, _HARU, "fuel_can")
        assert _owns(runtime, _GEN, "fuel_can")

    def test_cannot_take_what_they_do_not_have(self, runtime) -> None:
        """ミオが持っていない燃料の缶を奪おうとすると断られる。"""
        _place(runtime, _MIO, "village_square")
        _place(runtime, _GEN, "village_square")

        done, message = _try_on(runtime, _GEN, _MIO, "pickpocket", item="燃料の缶")

        assert not done
        assert message == "相手はそれを持っていない。"
        assert not _owns(runtime, _GEN, "fuel_can")

    def test_taking_again_needs_a_pause(self, runtime) -> None:
        """奪った直後にもう 1 つ奪おうとすると断られ、間隔の tick が経つと奪える。"""
        _place(runtime, _HARU, "village_square")
        _place(runtime, _GEN, "village_square")
        _try_on(runtime, _GEN, _HARU, "pickpocket", item="燃料の缶")

        right_after, _ = _try_on(runtime, _GEN, _HARU, "pickpocket", item="カンテラ")
        _ticks(runtime, _STEAL_COOLDOWN)
        after_the_pause, _ = _try_on(runtime, _GEN, _HARU, "pickpocket", item="カンテラ")

        assert (right_after, after_the_pause) == (False, True)

    def test_take_from_someone_who_is_down(self, runtime) -> None:
        """倒れているハルからも、ゲンが燃料の缶を奪える。"""
        _place(runtime, _HARU, "village_square")
        _place(runtime, _GEN, "village_square")
        _place(runtime, _SAYO, "village_square")
        _knock_down(runtime, _SAYO, _HARU)

        done, message = _try_on(runtime, _GEN, _HARU, "loot_from_downed", item="燃料の缶")

        assert done, message
        assert _owns(runtime, _GEN, "fuel_can")

    def test_taking_from_the_downed_also_needs_a_pause(self, runtime) -> None:
        """倒れているハルから燃料の缶を奪った直後は、カンテラを奪えず、間隔の tick が経つと奪える。"""
        for pid in (_HARU, _GEN, _SAYO):
            _place(runtime, pid, "village_square")
        _knock_down(runtime, _SAYO, _HARU)
        _try_on(runtime, _GEN, _HARU, "loot_from_downed", item="燃料の缶")

        right_after, _ = _try_on(runtime, _GEN, _HARU, "loot_from_downed", item="カンテラ")
        _ticks(runtime, _STEAL_COOLDOWN)
        after_the_pause, _ = _try_on(runtime, _GEN, _HARU, "loot_from_downed", item="カンテラ")

        assert (right_after, after_the_pause) == (False, True)

    def test_cannot_take_from_someone_in_the_cage(self, runtime) -> None:
        """籠に乗り込んだハルからは、物を奪えない。籠の席を奪って乗り込む抜け道にしないため。"""
        _board(runtime, _HARU)
        _place(runtime, _GEN, "lift_landing")

        done, message = _try_on(runtime, _GEN, _HARU, "pickpocket", item="燃料の缶")

        assert not done
        assert message == "籠の中の相手には手が届かない。"
        assert _owns(runtime, _HARU, "fuel_can")

    def test_cannot_take_from_someone_knocked_down_in_the_cage(self, runtime) -> None:
        """籠に乗り込んだハルを殴り倒しても、倒れたハルから籠の中の場所は奪えない。"""
        _board(runtime, _HARU)
        _place(runtime, _GEN, "lift_landing")
        _knock_down(runtime, _GEN, _HARU)

        done, message = _try_on(runtime, _GEN, _HARU, "loot_from_downed", item="籠の中の場所")

        assert not done
        assert message == "籠の中の相手には手が届かない。"
        assert not _owns(runtime, _GEN, "lift_berth")

    def test_in_the_light_the_onlooker_sees_who_took_it(self, runtime) -> None:
        """明るい村の広場で奪うと、見ていたサヨに奪った人と奪われた人の名前が届く。"""
        for pid in (_HARU, _GEN, _SAYO):
            _place(runtime, pid, "village_square")
        before = len(_prose(runtime, _SAYO))

        _try_on(runtime, _GEN, _HARU, "pickpocket", item="燃料の缶")

        seen = [line for line in _prose(runtime, _SAYO)[before:] if "荷" in line]
        assert [line for line in seen if "ゲン" in line and "ハル" in line] != []

    def test_in_the_dark_no_one_sees_who_took_it(self, runtime) -> None:
        """灯りの無い機械室で奪うと、見ていたサヨにも奪われたハルにも、奪った人の名前は届かない。"""
        for pid in (_HARU, _GEN, _SAYO):
            _place(runtime, pid, "machine_room")
            _drop(runtime, pid, "lamp")
        before = {p: len(_prose(runtime, p)) for p in (_HARU, _SAYO)}

        done, message = _try_on(runtime, _GEN, _HARU, "pickpocket", item="燃料の缶")

        assert done, message
        for pid in (_HARU, _SAYO):
            heard = [line for line in _prose(runtime, pid)[before[pid]:] if "荷" in line]
            assert heard, pid
            assert [line for line in heard if "ゲン" in line] == [], pid

    def test_in_the_dark_no_one_sees_who_struck(self, runtime) -> None:
        """灯りの無い機械室で殴ると、見ていたサヨに殴った人の名前は届かない。"""
        for pid in (_HARU, _GEN, _SAYO):
            _place(runtime, pid, "machine_room")
            _drop(runtime, pid, "lamp")
        before = len(_prose(runtime, _SAYO))

        _strike(runtime, _GEN, _HARU)

        heard = [line for line in _prose(runtime, _SAYO)[before:] if "殴" in line]
        assert heard
        assert [line for line in heard if "ゲン" in line] == []


def _prompt_text(runtime, pid: PlayerId) -> str:
    return "\n".join(str(m.get("content", "")) for m in runtime.build_full_prompt(pid)["messages"])


class TestHostileActsStayHidden:
    """攻撃と奪う操作を足しても、相手の存在を伏せる設定が崩れないことを保証する。"""

    def test_hostile_acts_are_offered_only_on_someone_here(self, runtime) -> None:
        """同じ場所にいるゲンの行には「殴りかかる」が出て、ゲンが別の場所へ移ると「殴りかかる」は出ない。"""
        _place(runtime, _HARU, "village_square")
        _place(runtime, _GEN, "village_square")
        together = _prompt_text(runtime, _HARU)
        _place(runtime, _GEN, "smithy")
        apart = _prompt_text(runtime, _HARU)

        assert any("ゲン" in line and "殴りかかる" in line for line in together.splitlines())
        assert "殴りかかる" not in apart

    def test_hostile_act_texts_mention_no_beast_or_sector(self) -> None:
        """攻撃と奪う操作の表示名や見ていた人への文に、獣を呼ぶことや区画のことを書かない。物音がしたことは、その場で聞こえる事実なので書く。"""
        texts = json.dumps(_raw()["player_interactions"], ensure_ascii=False)

        assert [w for w in ("獣", "目を覚", "眠", "区画", "呼") if w in texts] == []

    def test_every_precondition_has_its_own_failure_message(self) -> None:
        """人を対象にした操作と籠の操作の前提条件には、すべて断られたときの文がある。"""
        raw = _raw()
        lift = next(
            o for s in raw["spots"] for o in s.get("interior", {}).get("objects", []) if o["id"] == "lift"
        )
        interactions = raw["player_interactions"] + lift["interactions"]

        missing = [
            (i["action_name"], c["condition_type"])
            for i in interactions
            for c in i.get("preconditions", [])
            if not c.get("failure_message")
        ]
        assert missing == []
