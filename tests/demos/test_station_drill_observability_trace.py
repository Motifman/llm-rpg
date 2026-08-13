"""長走 run の空間分散・移動・会議時間を trace だけで測れることを保証する。"""

from pathlib import Path
from typing import Any

import pytest

from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.application.world_graph.game_phase_store import (
    GamePhaseTransitionException,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


_SCENARIO = Path(__file__).resolve().parents[2] / "data/scenarios/station_drill.json"
_MORI = PlayerId(1)
_KUZE = PlayerId(3)


class _CapturingRecorder:
    """record 呼び出しを kind と payload の組で保持する。"""

    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, Any]]] = []

    def record(self, kind: str, **payload: Any) -> None:
        self.records.append((kind, dict(payload)))


def _records(recorder: _CapturingRecorder, kind: str) -> list[dict[str, Any]]:
    return [payload for actual, payload in recorder.records if actual == kind]


def test_each_tick_records_all_spot_occupancies_and_player_travel_totals() -> None:
    """各 tick は無人室を含む9室の在室数と、各人の累積移動 tick を残す。"""
    runtime = create_world_runtime(_SCENARIO)
    recorder = _CapturingRecorder()
    runtime.set_trace_recorder(recorder)

    runtime.do_move(_MORI, "observatory")
    runtime.advance_tick()
    runtime.advance_tick()

    metrics = _records(recorder, TraceEventKind.WORLD_SPATIAL_METRICS)
    assert len(metrics) == 2
    assert all(len(row["spot_occupancy"]) == 9 for row in metrics)
    assert metrics[-1]["occupancy_scope"] == "meeting_eligible_players"
    assert metrics[-1]["travel_scope"] == "all_players_including_departed"
    assert sum(row["player_count"] for row in metrics[-1]["spot_occupancy"]) == 8
    assert metrics[0]["cumulative_travel_ticks_by_player"]["1"] == 1
    assert metrics[1]["cumulative_travel_ticks_by_player"]["1"] == 2
    assert set(metrics[-1]["cumulative_travel_ticks_by_player"]) == {
        str(int(pid)) for pid in runtime.get_player_ids()
    }


def test_spot_occupancy_excludes_a_fallen_body_and_departed_player() -> None:
    """在室数は遺体と幽霊を数えず、会話に参加できる社会密度を表す。"""
    runtime = create_world_runtime(_SCENARIO)
    recorder = _CapturingRecorder()
    runtime.set_trace_recorder(recorder)

    runtime.do_interact_with_player(_KUZE, _MORI, "strike_down")
    runtime.advance_tick()

    metrics = _records(recorder, TraceEventKind.WORLD_SPATIAL_METRICS)
    assert sum(row["player_count"] for row in metrics[-1]["spot_occupancy"]) == 7


def test_meeting_trace_keeps_interval_location_reason_and_cumulative_ticks() -> None:
    """会議ごとの開始・終了・契機・場所・理由と累積会議 tick を復元できる。"""
    runtime = create_world_runtime(_SCENARIO)
    recorder = _CapturingRecorder()
    runtime.set_trace_recorder(recorder)
    meeting_spot_id = runtime.get_player_spot_id(_MORI)

    runtime.begin_meeting(initiator_player_id=_MORI, trigger="body_report")
    runtime.advance_tick()
    runtime.advance_tick()
    runtime.end_meeting(reason="vote_concluded")
    runtime._time_provider.advance_tick(3)
    runtime.begin_meeting(initiator_player_id=_MORI, trigger="emergency_button")
    runtime._time_provider.advance_tick(1)
    runtime.end_meeting(reason="silence")

    started = _records(recorder, TraceEventKind.MEETING_STARTED)
    ended = _records(recorder, TraceEventKind.MEETING_ENDED)
    assert len(started) == 2
    assert started[0] == {
        "tick": 0,
        "trigger": "body_report",
        "spot_id": meeting_spot_id,
        "spot_name": "集会室",
        "initiator_player_id": 1,
    }
    assert len(ended) == 2
    assert ended[0] == {
        "tick": 2,
        "started_at_tick": 0,
        "ended_at_tick": 2,
        "trigger": "body_report",
        "spot_id": meeting_spot_id,
        "spot_name": "集会室",
        "end_reason": "vote_concluded",
        "duration_ticks": 2,
        "cumulative_meeting_ticks": 2,
    }
    assert ended[1]["duration_ticks"] == 1
    assert ended[1]["cumulative_meeting_ticks"] == 3


def test_rejected_phase_transitions_do_not_create_meeting_trace() -> None:
    """状態が動かない拒否では、会議の開始・終了 trace も増やさない。"""
    runtime = create_world_runtime(_SCENARIO)
    recorder = _CapturingRecorder()
    runtime.set_trace_recorder(recorder)

    with pytest.raises(GamePhaseTransitionException, match="会議中ではない"):
        runtime.end_meeting(reason="silence")
    runtime.begin_meeting(initiator_player_id=_MORI, trigger="body_report")
    with pytest.raises(GamePhaseTransitionException, match="すでに始まっています"):
        runtime.begin_meeting(initiator_player_id=_MORI, trigger="body_report")

    assert len(_records(recorder, TraceEventKind.MEETING_STARTED)) == 1
    assert _records(recorder, TraceEventKind.MEETING_ENDED) == []
