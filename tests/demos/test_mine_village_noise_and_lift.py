"""廃坑の山村 (`mine_village_v1`) の音と獣、遠くに聞こえる手がかり、金庫、昇降機が、設計の決まりどおりに働くことを保証する。

設計は docs/mine_village_scenario_design.md の「足す仕掛け: 音と獣」「相手の前進が聞こえる」
「勝つまでの道」と、決まりの一覧の R4 (発電機を温めないと昇降機が動かない)、
R5 (音を立てると、その区画に獣が現れる)、R8 (金庫の番号の手がかりが事務所に隠れている)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.application.world_graph.world_flag_state import (
    WorldFlagMutationContext,
    WorldFlagMutationSource,
)
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.enum.player_outcome_enum import PlayerOutcomeEnum
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.exception.spot_graph_exception import (
    InteractionNotAllowedException,
    InteractionNotFoundException,
)
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_SCENARIO = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "mine_village_v1.json"

_HARU, _MIO, _GEN, _SAYO = (PlayerId(i) for i in range(1, 5))

#: R5: 区画 → (音を立てる水門, 獣が現れる場所)。
_SECTORS = {
    "north": ("gate_a", "north_tunnel"),
    "south": ("gate_b", "south_tunnel"),
    "deep": ("gate_c", "mid_junction"),
}

#: 仮の値 (設計の「未決」)。
_NOISE_THRESHOLD = 3
_SLEEP_TICKS = 20
_WARM_TICKS = 6
#: 燃料の缶 1 つで発電機にたまる量と、ポンプ 1 回で使う量 (設計の「未決」)。
_CAN_FUEL = 3
_PUMP_FUEL = 1
_SAFE_CODE = "1907"


@pytest.fixture()
def runtime():
    return create_world_runtime(_SCENARIO)


def _place(runtime, pid: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    entity = EntityId.create(int(pid))
    graph.unplace_entity(entity)
    graph.place_entity(entity, SpotId.create(runtime.id_mapper.get_int("spot", spot)))
    runtime._spot_graph_repo.save(graph)


def _act(runtime, pid: PlayerId, spot: str, obj: str, action: str, **params: str):
    _place(runtime, pid, spot)
    return runtime.do_interact(pid, obj, action, interaction_parameters=params or None)


def _try(runtime, pid: PlayerId, spot: str, obj: str, action: str, **params: str) -> tuple[str, str]:
    """操作を試し、("done" / "refused" / "absent", 返った文) を返す。

    "refused" は前提条件で断られた、"absent" はその操作がいま出ていない
    (名前の打ち間違いを含む)。断られたことを確かめるテストは "refused" を見る。
    """
    try:
        result = _act(runtime, pid, spot, obj, action, **params)
    except InteractionNotAllowedException as exc:
        return "refused", str(exc)
    except InteractionNotFoundException as exc:
        return "absent", str(exc)
    return "done", "\n".join(result.messages)


def _ticks(runtime, n: int) -> None:
    for _ in range(n):
        runtime.advance_tick()


def _beast_spots(runtime) -> list[str]:
    graph = runtime._spot_graph_repo.find_graph()
    return sorted(runtime.id_mapper.get_str("spot", s.value) for s in graph.monster_spot_mapping().values())


def _make_noise(runtime, sector: str, times: int) -> None:
    """区画の水門を開け閉めして、1 tick に 1 回ずつ音を立てる。"""
    gate, spot = _SECTORS[sector]
    for _ in range(times):
        is_open = f"{gate}_open" in runtime._world_flag_state.as_frozen_set()
        _act(runtime, _HARU, spot, gate, "close_gate" if is_open else "open_gate")
        _ticks(runtime, 1)


def _hp(runtime, pid: PlayerId) -> int:
    return int(runtime._player_status_repo.find_by_id(pid).hp.value)


def _observations(runtime, pid: PlayerId, kind: str) -> list[str]:
    return [
        e.output.prose
        for e in runtime._obs_buffer.get_observations(pid)
        if e.output.structured.get("type") == kind
    ]


def _fuel_and_start_generator(runtime) -> None:
    """北のハルの燃料の缶 (発電機の燃料 `_CAN_FUEL` 分) を注ぎ、次の tick に発電機を動かす。"""
    _act(runtime, _HARU, "machine_room", "generator", "pour_fuel_can")
    _ticks(runtime, 1)
    _act(runtime, _HARU, "machine_room", "generator", "start_generator")


def _board(runtime, pid: PlayerId) -> None:
    """乗り場で籠に乗り込む。昇降機の操作盤は籠の中にあり、脱出できるのも乗り込んだ人だけ。"""
    _act(runtime, pid, "lift_landing", "lift", "board_lift")


def _open_safe(runtime, pid: PlayerId = _GEN) -> None:
    _act(runtime, pid, "company_office", "office_safe", "open_safe", code=_SAFE_CODE)



def _clear_gas(runtime) -> None:
    """掘り場のガスを抜く。ガスは確率で溜まり (R6、test_mine_village_light_gas_and_food.py)、溜まっていると予備の燃料が取れない。燃料の量を見るテストを偶然に左右させないため。"""
    if "gas_present" in runtime._world_flag_state.as_frozen_set():
        runtime._world_flag_state.remove(
            "gas_present",
            context=WorldFlagMutationContext(source=WorldFlagMutationSource.SCENARIO_EVENT, actor_player_id=None),
        )

class TestNoiseWakesTheBeastOfThatSector:
    """R5: 区画ごとに音が積もり、閾値に届くとその区画の決まった場所に獣が現れることを保証する。"""

    def test_beast_attacks_someone_where_it_appears(self, runtime) -> None:
        """北の坑道にいるのがミオだけなら、ミオは獣が現れてから 3 tick のうちに襲われて HP が減り、南の坑道にいるサヨは減らない。"""
        _place(runtime, _MIO, "north_tunnel")
        _place(runtime, _SAYO, "south_tunnel")
        before = {p: _hp(runtime, p) for p in (_MIO, _SAYO)}
        _make_noise(runtime, "north", _NOISE_THRESHOLD)
        # 獣は同じ場所の人からランダムに標的を選ぶので、音を立てたハルを残すとミオが選ばれないことがある
        _place(runtime, _HARU, "village_square")

        _ticks(runtime, 3)

        assert _hp(runtime, _MIO) < before[_MIO]
        assert _hp(runtime, _SAYO) == before[_SAYO]

    def test_beast_wakes_again_after_sleeping(self, runtime) -> None:
        """眠りに戻った北の獣は、また閾値の回数の音を立てると現れ、そこからちょうど `_SLEEP_TICKS` tick でまた眠る。"""
        _make_noise(runtime, "north", _NOISE_THRESHOLD)
        _ticks(runtime, _SLEEP_TICKS)

        _make_noise(runtime, "north", _NOISE_THRESHOLD)
        awake_again = _beast_spots(runtime)
        _ticks(runtime, _SLEEP_TICKS - 1)
        still_awake = _beast_spots(runtime)
        _ticks(runtime, 1)

        assert awake_again == ["north_tunnel"]
        assert still_awake == ["north_tunnel"]
        assert _beast_spots(runtime) == []

    def test_beast_description_does_not_tell_what_wakes_it(self) -> None:
        """獣の説明文は、現れるたびにプロンプトに出るので、音や物音で目覚めることを書かない。"""
        description = _raw()["monsters"]["templates"][0]["description"]

        assert not any(word in description for word in ("音", "目を覚", "起き"))

    def test_more_noise_while_awake_brings_no_second_beast(self, runtime) -> None:
        """獣が起きている間にさらに閾値の回数の音を立てても、北の獣は 1 頭のまま。"""
        _make_noise(runtime, "north", _NOISE_THRESHOLD)

        _make_noise(runtime, "north", _NOISE_THRESHOLD)

        assert _beast_spots(runtime) == ["north_tunnel"]

    def test_no_beast_at_start(self, runtime) -> None:
        """始まった時点では、どこにも獣はいない。"""
        _ticks(runtime, 1)

        assert _beast_spots(runtime) == []

    @pytest.mark.parametrize("sector", sorted(_SECTORS))
    def test_beast_appears_where_the_noise_reached_the_threshold(self, runtime, sector) -> None:
        """区画で音を閾値 - 1 回立てても獣は出ず、閾値の回数目の音を立てたその tick のうちに、その区画の出現場所に 1 頭だけ現れる。"""
        _make_noise(runtime, sector, _NOISE_THRESHOLD - 1)
        before = _beast_spots(runtime)

        _make_noise(runtime, sector, 1)

        assert before == []
        assert _beast_spots(runtime) == [_SECTORS[sector][1]]

    def test_noise_does_not_add_up_across_sectors(self, runtime) -> None:
        """北で閾値 - 1 回、南で閾値 - 1 回の音を立てても、どちらの区画にも獣は出ない。"""
        _make_noise(runtime, "north", _NOISE_THRESHOLD - 1)
        _make_noise(runtime, "south", _NOISE_THRESHOLD - 1)
        _ticks(runtime, 1)

        assert _beast_spots(runtime) == []

    def test_machines_and_the_timber_are_loud_in_the_deep(self, runtime) -> None:
        """発電機を動かす、ポンプを動かす、支柱を倒すは、どれも深いところの音になり、3 つで分岐に獣が出る。"""
        _fuel_and_start_generator(runtime)
        _ticks(runtime, 1)
        _act(runtime, _HARU, "machine_room", "pump", "run_pump")
        _ticks(runtime, 1)
        _act(runtime, _GEN, "timber_passage", "old_timber", "fell_timber")
        _ticks(runtime, 2)

        assert _beast_spots(runtime) == ["mid_junction"]

    def test_the_beast_goes_back_to_sleep(self, runtime) -> None:
        """現れた獣は、現れてから `_SLEEP_TICKS` - 1 tick 後はまだいて、ちょうど `_SLEEP_TICKS` tick 後にいなくなる。"""
        _make_noise(runtime, "north", _NOISE_THRESHOLD)

        _ticks(runtime, _SLEEP_TICKS - 1)
        still_awake = _beast_spots(runtime)
        _ticks(runtime, 1)

        assert still_awake == ["north_tunnel"]
        assert _beast_spots(runtime) == []

    def test_noise_counts_again_from_zero_after_the_beast_sleeps(self, runtime) -> None:
        """獣が眠りに戻ったあとは、閾値 - 1 回の音では獣はまた出ない。"""
        _make_noise(runtime, "north", _NOISE_THRESHOLD)
        _ticks(runtime, _SLEEP_TICKS + 2)

        _make_noise(runtime, "north", _NOISE_THRESHOLD - 1)
        _ticks(runtime, 1)

        assert _beast_spots(runtime) == []


class TestDistantCuesTellSomeoneIsAhead:
    """相手の前進が聞こえる: 機械の唸りと金庫の鐘が、離れた場所の人に、誰がやったかを伏せて届くことを保証する。

    遠景の手がかり (distant_cues) は屋外の場所にしか届かないので、全員に届く出来事の知らせで代えている。
    """

    def test_generator_hum_reaches_someone_deep_in_the_other_tunnel(self, runtime) -> None:
        """北のハルが発電機を動かすと、次の tick に南の横坑の奥にいるゲンに唸りが 1 回だけ届き、ハルの名前は出ない。"""
        _place(runtime, _GEN, "south_adit_end")

        _fuel_and_start_generator(runtime)
        _ticks(runtime, 3)

        heard = [h for h in _observations(runtime, _GEN, "scenario_event") if "唸りが響いてきた" in h]
        assert len(heard) == 1
        assert "ハル" not in heard[0]

    def test_hum_is_heard_again_after_a_restart(self, runtime) -> None:
        """燃料が尽きて止まった発電機をもう一度動かすと、唸りがまた届く。"""
        _place(runtime, _GEN, "south_adit_end")
        _fuel_and_start_generator(runtime)
        _ticks(runtime, 1)
        for _ in range(_CAN_FUEL // _PUMP_FUEL):
            _act(runtime, _HARU, "machine_room", "pump", "run_pump")
            _ticks(runtime, 1)
        _ticks(runtime, 1)

        _clear_gas(runtime)
        _act(runtime, _HARU, "gas_chamber", "spare_fuel_crate", "take_spare_fuel_can")
        _act(runtime, _HARU, "machine_room", "generator", "pour_fuel_can")
        _ticks(runtime, 1)
        _act(runtime, _HARU, "machine_room", "generator", "start_generator")
        _ticks(runtime, 1)

        heard = [h for h in _observations(runtime, _GEN, "scenario_event") if "唸りが響いてきた" in h]
        assert len(heard) == 2

    def test_safe_bell_reaches_someone_far_away(self, runtime) -> None:
        """南のゲンが金庫を開けると、次の tick に北の竪坑口にいるハルに鐘が届き、ゲンの名前は出ない。"""
        _place(runtime, _HARU, "north_shaft_head")

        _open_safe(runtime)
        _ticks(runtime, 1)

        heard = [h for h in _observations(runtime, _HARU, "scenario_event") if "鐘" in h]
        assert len(heard) == 1
        assert "ゲン" not in heard[0]


class TestSafeAndKey:
    """R8: 金庫は番号でしか開かず、番号の手がかりは事務所の机にあり、開けると起動鍵が手に入ることを保証する。"""

    def test_wrong_code_is_refused(self, runtime) -> None:
        """違う番号では金庫は開かず、起動鍵も手に入らない。"""
        outcome, message = _try(runtime, _HARU, "company_office", "office_safe", "open_safe", code="0000")

        assert outcome == "refused"
        assert "びくともしない" in message
        assert not _has_key(runtime, _HARU)

    def test_desk_holds_the_code(self, runtime) -> None:
        """事務机の引き出しを探ると、金庫の番号が書かれた紙が見つかる。"""
        result = _act(runtime, _HARU, "company_office", "office_desk", "search_desk_drawer")

        assert any(_SAFE_CODE in m for m in result.messages)

    def test_right_code_gives_the_key_once(self, runtime) -> None:
        """正しい番号で開けると起動鍵が手に入り、2 度目は断られる。"""
        _open_safe(runtime, _GEN)

        outcome, _message = _try(runtime, _SAYO, "company_office", "office_safe", "open_safe", code=_SAFE_CODE)

        assert outcome == "refused"
        assert _has_key(runtime, _GEN)

    def test_south_knows_the_code_north_does_not(self, runtime) -> None:
        """番号を知っているのは、人格の設定 (persona_prompt) にそれが書かれたチーム南の 2 人だけ。"""
        personas = {p["id"]: p["persona_prompt"] for p in _raw()["players"]}

        assert {pid for pid, text in personas.items() if _SAFE_CODE in text} == {"gen", "sayo"}


class TestLift:
    """R4 と脱出: 昇降機は起動鍵と温まった発電機と燃料 2 で動き、籠に乗り込んだ人だけが脱出することを保証する。"""

    def _ready(self, runtime) -> None:
        _open_safe(runtime, _HARU)
        _fuel_and_start_generator(runtime)
        _board(runtime, _HARU)

    def test_lift_refuses_before_the_generator_warms_up(self, runtime) -> None:
        """鍵と燃料 2 があっても、発電機を動かしてから `_WARM_TICKS` - 1 tick 後は、昇降機は動かない。断る文は、温める必要があることを漏らさない。"""
        self._ready(runtime)
        _ticks(runtime, _WARM_TICKS - 1)

        outcome, message = _try(runtime, _HARU, "lift_landing", "lift", "start_lift")

        assert outcome == "refused"
        assert "温" not in message

    def test_lift_starts_once_the_generator_is_warm(self, runtime) -> None:
        """発電機を動かしてからちょうど `_WARM_TICKS` tick 後に、昇降機は動く。"""
        self._ready(runtime)
        _ticks(runtime, _WARM_TICKS)

        outcome, _message = _try(runtime, _HARU, "lift_landing", "lift", "start_lift")

        assert outcome == "done"

    def test_lift_refuses_without_the_key(self, runtime) -> None:
        """発電機が温まっていても、起動鍵を持っていなければ動かない。"""
        _fuel_and_start_generator(runtime)
        _board(runtime, _HARU)
        _ticks(runtime, _WARM_TICKS + 1)

        outcome, message = _try(runtime, _HARU, "lift_landing", "lift", "start_lift")

        assert outcome == "refused"
        assert "鍵" in message

    def test_anyone_holding_the_key_can_start_the_lift(self, runtime) -> None:
        """金庫を開けたのが南のゲンでも、鍵を持つゲンが乗り場で動かせば昇降機は動く。開けた人と動かす人は鍵でつながる。"""
        _open_safe(runtime, _GEN)
        _fuel_and_start_generator(runtime)
        _board(runtime, _GEN)
        _ticks(runtime, _WARM_TICKS)

        outcome, _message = _try(runtime, _GEN, "lift_landing", "lift", "start_lift")

        assert outcome == "done"

    def test_lift_refuses_once_the_generator_has_stopped(self, runtime) -> None:
        """温まったあとにポンプで燃料を使い切って発電機が止まると、燃料を足しても温め直すまで昇降機は動かない。"""
        self._ready(runtime)
        _ticks(runtime, _WARM_TICKS)
        for _ in range(_CAN_FUEL // _PUMP_FUEL):
            _act(runtime, _HARU, "machine_room", "pump", "run_pump")
            _ticks(runtime, 1)
        _clear_gas(runtime)
        _act(runtime, _HARU, "gas_chamber", "spare_fuel_crate", "take_spare_fuel_can")
        _act(runtime, _HARU, "machine_room", "generator", "pour_fuel_can")
        _ticks(runtime, 1)

        outcome, _message = _try(runtime, _HARU, "lift_landing", "lift", "start_lift")

        assert outcome == "refused"

    def test_lift_refuses_with_too_little_fuel(self, runtime) -> None:
        """缶 1 つ分の燃料からポンプで燃料が 2 を下回るまで使うと、温まっていても昇降機は動かない。"""
        self._ready(runtime)
        _ticks(runtime, 1)
        for _ in range((_CAN_FUEL - 1) // _PUMP_FUEL):
            _act(runtime, _HARU, "machine_room", "pump", "run_pump")
            _ticks(runtime, 1)
        _ticks(runtime, _WARM_TICKS + 1)

        outcome, message = _try(runtime, _HARU, "lift_landing", "lift", "start_lift")

        assert outcome == "refused"
        assert "揺れただけ" in message

    def test_people_on_the_landing_escape_and_the_rest_are_left(self, runtime) -> None:
        """昇降機を動かすと、籠に乗り込んだハルとゲンは脱出し、乗り込まなかったミオとサヨは取り残され、ゲームが終わる。"""
        self._ready(runtime)
        _ticks(runtime, _WARM_TICKS + 1)
        _board(runtime, _GEN)
        _place(runtime, _MIO, "machine_room")
        _place(runtime, _SAYO, "company_office")

        _act(runtime, _HARU, "lift_landing", "lift", "start_lift")
        _ticks(runtime, 1)

        registry = runtime._player_outcome_registry
        assert {p: registry.get_outcome(p) for p in (_HARU, _MIO, _GEN, _SAYO)} == {
            _HARU: PlayerOutcomeEnum.RESCUED,
            _MIO: PlayerOutcomeEnum.STRANDED,
            _GEN: PlayerOutcomeEnum.RESCUED,
            _SAYO: PlayerOutcomeEnum.STRANDED,
        }
        assert runtime.check_game_end().is_ended

    def test_lift_runs_only_once(self, runtime) -> None:
        """一度動いた昇降機は、燃料と鍵と温まりがそろっていても、二度と動かないと断る。"""
        self._ready(runtime)
        _ticks(runtime, _WARM_TICKS + 1)
        _act(runtime, _HARU, "lift_landing", "lift", "start_lift")

        outcome, message = _try(runtime, _HARU, "lift_landing", "lift", "start_lift")

        assert outcome == "refused"
        assert "二度と動かない" in message


class _CapturingRecorder(NullTraceRecorder):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[Any] = []

    def record(self, kind: str, **kwargs: Any):
        event = super().record(kind, **kwargs)
        self.events.append(event)
        return event


def _flag_changes(recorder: _CapturingRecorder, flag: str) -> list[tuple[bool, str, int | None]]:
    return [
        (e.payload["set"], e.payload["source"], e.payload["actor_player_id"])
        for e in recorder.events
        if e.kind == TraceEventKind.WORLD_FLAG_CHANGED and e.payload["flag_name"] == flag
    ]


class TestNoiseAndLiftLeaveATrace:
    """獣が目覚めた・眠ったことと、昇降機を動かした人が trace から読めることを保証する。決まりを使えたかの判定に使う。"""

    def test_beast_waking_and_sleeping_are_recorded(self, runtime) -> None:
        """北で音が閾値に届くと獣のフラグが出来事として立ち、眠りに戻ると出来事として消える。"""
        recorder = _CapturingRecorder()
        runtime.set_trace_recorder(recorder)

        _make_noise(runtime, "north", _NOISE_THRESHOLD)
        _ticks(runtime, _SLEEP_TICKS)

        assert _flag_changes(recorder, "beast_north_awake") == [
            (True, "scenario_event", None),
            (False, "scenario_event", None),
        ]

    def test_lift_departure_names_who_started_it(self, runtime) -> None:
        """昇降機が動いたことは、動かしたハルの名で trace に残る。"""
        _open_safe(runtime, _HARU)
        _fuel_and_start_generator(runtime)
        _board(runtime, _HARU)
        _ticks(runtime, _WARM_TICKS)
        recorder = _CapturingRecorder()
        runtime.set_trace_recorder(recorder)

        _act(runtime, _HARU, "lift_landing", "lift", "start_lift")

        assert _flag_changes(recorder, "lift_departed") == [(True, "spot_interaction", int(_HARU))]


def _raw() -> dict:
    import json

    return json.loads(_SCENARIO.read_text(encoding="utf-8"))


def _has_key(runtime, pid: PlayerId) -> bool:
    from ai_rpg_world.application.world_graph.spot_inventory_helpers import (
        collect_owned_item_spec_ids_from_inventory,
    )

    key = runtime.id_mapper.get_int("item_spec", "lift_key")
    owned = collect_owned_item_spec_ids_from_inventory(
        runtime._player_inventory_repo.find_by_id(pid), runtime._item_repo
    )
    return any(int(getattr(s, "value", s)) == key for s in owned)
