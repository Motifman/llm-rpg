"""廃坑の山村 (`mine_village_v1`) で、移動中に通路が閉じても run が止まらず、本人に手がかりが届き trace に残ることを保証する (#1559)。

`var/runs/mine_v1_002` では、ゲンが防火扉を通って北の坑道へ向かう途中にハルが北側の閂を掛け、
渡る tick の例外で run 全体が止まった。同じ形は水門で通路が沈んだときにも起きる。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.trace import NullTraceRecorder, TraceEventKind
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.domain.player.value_object.player_id import PlayerId
from ai_rpg_world.domain.world.value_object.spot_id import SpotId
from ai_rpg_world.domain.world_graph.value_object.entity_id import EntityId

_SCENARIO = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "mine_village_v1.json"

_HARU = PlayerId(1)
_GEN = PlayerId(3)


class _CapturingRecorder(NullTraceRecorder):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[Any] = []

    def record(self, kind: str, **kwargs: Any):
        event = super().record(kind, **kwargs)
        self.events.append(event)
        return event


@pytest.fixture()
def runtime():
    rt = create_world_runtime(_SCENARIO)
    rt.set_trace_recorder(_CapturingRecorder())
    return rt


def _spot_id(runtime, spot: str) -> SpotId:
    return SpotId.create(runtime.id_mapper.get_int("spot", spot))


def _place(runtime, pid: PlayerId, spot: str) -> None:
    graph = runtime._spot_graph_repo.find_graph()
    entity = EntityId.create(int(pid))
    graph.unplace_entity(entity)
    graph.place_entity(entity, _spot_id(runtime, spot))
    runtime._spot_graph_repo.save(graph)


def _spot_of(runtime, pid: PlayerId) -> SpotId:
    return runtime._spot_graph_repo.find_graph().get_entity_spot(EntityId.create(int(pid)))


def _is_traveling(runtime, pid: PlayerId) -> bool:
    status = runtime._player_status_repo.find_by_id(pid)
    nav = status.spot_navigation_state
    return nav is not None and nav.is_traveling


def _blocked_observations(runtime, pid: PlayerId) -> list[Any]:
    return [
        entry.output
        for entry in runtime._obs_buffer.get_observations(pid)
        if entry.output.structured.get("type") == "travel_blocked"
    ]


def _blocked_traces(runtime) -> list[Any]:
    return [
        e for e in runtime._trace_recorder.events if e.kind == TraceEventKind.TRAVEL_BLOCKED
    ]


def _gen_heads_north_and_haru_bars_the_door(runtime) -> None:
    """ゲンが防火扉 (2 tick) へ踏み出した tick に、ハルが北側の閂を掛ける。"""
    _place(runtime, _GEN, "south_tunnel")
    _place(runtime, _HARU, "north_tunnel")
    runtime.do_move(_GEN, "north_tunnel")
    runtime.do_interact(_HARU, "fire_door_bar_north", "bar_fire_door_north")
    for _ in range(3):
        runtime.advance_tick()


def _gen_heads_into_the_adit_and_haru_opens_gate_a(runtime) -> None:
    """ゲンが南の横坑の奥 (3 tick) へ踏み出した tick に、ハルが水門 A を開けて道を沈める。"""
    _place(runtime, _GEN, "south_tunnel")
    _place(runtime, _HARU, "north_tunnel")
    runtime.do_move(_GEN, "south_adit_end")
    runtime.do_interact(_HARU, "gate_a", "open_gate_a")
    for _ in range(4):
        runtime.advance_tick()


class TestBarredFireDoorMidTravel:
    """防火扉を移動中に閂で閉じられた場面を、本物の組み立て経路で再現する。"""

    def test_gen_stays_south_without_exception_when_fire_door_is_barred(self, runtime) -> None:
        """渡る tick に例外を出さず、ゲンは南の坑道で止まり、移動中ではなくなる。"""
        _gen_heads_north_and_haru_bars_the_door(runtime)

        assert _spot_of(runtime, _GEN) == _spot_id(runtime, "south_tunnel")
        assert not _is_traveling(runtime, _GEN)

    def test_gen_hears_the_door_is_shut_and_gets_a_turn(self, runtime) -> None:
        """ゲンにだけ「防火扉は閉ざされていて」で始まり「その先へは行けない。」で終わる観測が 1 件届き、手番が積まれる。"""
        _gen_heads_north_and_haru_bars_the_door(runtime)

        observations = _blocked_observations(runtime, _GEN)
        assert [o.prose for o in observations] == [
            "防火扉は閉ざされていて、開かない。その先へは行けない。"
        ]
        assert observations[0].schedules_turn is True
        assert _blocked_observations(runtime, _HARU) == []

    def test_gen_history_records_the_abandoned_travel(self, runtime) -> None:
        """ゲンの行動履歴の最後は、移動を取りやめた失敗の行で、出発の行のままにならない。"""
        _gen_heads_north_and_haru_bars_the_door(runtime)

        latest = runtime._action_result_store.get_recent(_GEN, 1)[-1]
        assert latest.success is False
        assert latest.error_code == "TRAVEL_BLOCKED"
        assert "防火扉" in latest.action_summary
        assert "南の坑道" in latest.result_summary

    def test_blocked_texts_hide_who_closed_it_and_internal_ids(self, runtime) -> None:
        """観測と履歴の文に、閂を掛けたハルの名前と内部の番号が出ない。"""
        _gen_heads_north_and_haru_bars_the_door(runtime)

        observations = _blocked_observations(runtime, _GEN)
        latest = runtime._action_result_store.get_recent(_GEN, 1)[-1]
        assert len(observations) == 1
        assert latest.error_code == "TRAVEL_BLOCKED"
        texts = [
            observations[0].prose,
            observations[0].structured["message"],
            observations[0].structured["connection_name"],
            latest.action_summary,
            latest.result_summary,
        ]
        for text in texts:
            assert "ハル" not in text
            assert not any(ch.isdigit() for ch in text)

    def test_trace_records_who_where_and_why(self, runtime) -> None:
        """trace に travel_blocked が 1 件残り、ゲン・防火扉・区間の両端・行き先・理由が読める。"""
        _gen_heads_north_and_haru_bars_the_door(runtime)

        events = _blocked_traces(runtime)
        assert len(events) == 1
        event = events[0]
        assert event.player_id == int(_GEN)
        payload = event.payload
        assert payload["connection_name"] == "防火扉"
        assert payload["passage_kind"] == "DOOR"
        assert payload["passage_state"] == "LOCKED"
        assert payload["reason"] == "passage_closed"
        assert payload["from_spot_name"] == "南の坑道"
        assert payload["to_spot_name"] == "北の坑道"
        assert payload["destination_spot_name"] == "北の坑道"


class _RecordingTurnScheduler:
    def __init__(self) -> None:
        self.calls: list[tuple[PlayerId, Any]] = []

    def maybe_schedule(self, player_id: PlayerId, output: Any) -> None:
        self.calls.append((player_id, output))


class TestBlockedTravelerGetsATurn:
    """止まった本人の観測が、手番を積むスケジューラまで実際に渡ることを保証する。"""

    def test_turn_scheduler_receives_the_blocked_observation_for_gen(self, runtime) -> None:
        """閂で止まったゲンの手がかりの観測が、手番を積むスケジューラにゲン宛てで 1 回渡る。"""
        scheduler = _RecordingTurnScheduler()
        runtime.set_observation_turn_scheduler(scheduler)

        _gen_heads_north_and_haru_bars_the_door(runtime)

        blocked_calls = [
            (pid, output)
            for pid, output in scheduler.calls
            if output.structured.get("type") == "travel_blocked"
        ]
        assert [pid for pid, _ in blocked_calls] == [_GEN]
        assert blocked_calls[0][1].schedules_turn is True


class TestFloodedPassageMidTravel:
    """水門で通路が沈んだ場合も、防火扉と同じ扱いになることを保証する。"""

    def test_gen_stops_and_hears_the_way_is_blocked(self, runtime) -> None:
        """南の横坑の奥へ向かう途中で水門 A が開くと、ゲンは南の坑道で止まり、道が塞がった観測が届き、trace に障壁として残る。"""
        _gen_heads_into_the_adit_and_haru_opens_gate_a(runtime)

        assert _spot_of(runtime, _GEN) == _spot_id(runtime, "south_tunnel")
        assert not _is_traveling(runtime, _GEN)
        assert [o.prose for o in _blocked_observations(runtime, _GEN)] == [
            "南の坑道と南の横坑の奥の道は塞がっていて、通れない。その先へは行けない。"
        ]
        assert [
            (e.payload["passage_kind"], e.payload["passage_state"])
            for e in _blocked_traces(runtime)
        ] == [("BARRIER", "ACTIVE")]


class _FailingBlockedTraceRecorder(_CapturingRecorder):
    def record(self, kind: str, **kwargs: Any):
        if kind == TraceEventKind.TRAVEL_BLOCKED:
            raise RuntimeError("trace sink failed")
        return super().record(kind, **kwargs)


class TestBlockedReportSurvivesTraceFailure:
    """trace の記録が失敗しても、本人への観測・手番・行動履歴は失われないことを保証する。"""

    def test_observation_and_history_arrive_even_if_trace_fails(self) -> None:
        """travel_blocked の記録が例外を投げても run は止まらず、ゲンに手がかりの観測と取りやめの行が届く。"""
        runtime = create_world_runtime(_SCENARIO)
        runtime.set_trace_recorder(_FailingBlockedTraceRecorder())

        _gen_heads_north_and_haru_bars_the_door(runtime)

        assert len(_blocked_observations(runtime, _GEN)) == 1
        latest = runtime._action_result_store.get_recent(_GEN, 1)[-1]
        assert latest.error_code == "TRAVEL_BLOCKED"
