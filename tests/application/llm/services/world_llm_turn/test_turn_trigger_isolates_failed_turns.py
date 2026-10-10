"""run_scheduled_turns が 1 人のターンの例外を、世界の tick の方針に従って取りやめるか止めるかを保証する。"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from tests.support.trace_recorders import CollectingTraceRecorder

from ai_rpg_world.application.llm.contracts.dtos import LlmCommandResultDto
from ai_rpg_world.application.llm.services.world_llm_turn.turn_trigger import (
    WorldLlmTurnTrigger,
)
from ai_rpg_world.application.llm.services.world_llm_turn.types import LlmPhaseAResult
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.application.world_graph.world_tick_failure_isolation import (
    WorldTickFailureIsolator,
    WorldTickFailurePolicy,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_OK = LlmCommandResultDto(success=True, message="ok")


def _fail_for_player_1(player_id: PlayerId) -> LlmCommandResultDto:
    if player_id.value == 1:
        raise RuntimeError("prompt build failed")
    return _OK


def _trigger(
    policy: WorldTickFailurePolicy, recorder: CollectingTraceRecorder, *, workers: int
) -> WorldLlmTurnTrigger:
    wiring = MagicMock()
    wiring.turn_gate = None
    wiring.runtime.check_game_end.return_value.is_ended = False
    wiring.runtime.current_tick.return_value = 5
    wiring.runtime._runtime_config.llm_turn_parallel_workers = workers
    wiring.runtime._runtime_config.llm_meeting_serial_turns = False
    wiring.runtime.world_tick_failure_isolator = WorldTickFailureIsolator(
        policy=policy, trace_recorder_provider=lambda: recorder
    )
    wiring.run_turn.side_effect = _fail_for_player_1
    wiring.run_phase_a.side_effect = lambda pid: LlmPhaseAResult(
        player_id=pid, prompt={}, tools_payload=[], tool_call=None
    )
    wiring.run_phase_b.side_effect = lambda phase_a: _fail_for_player_1(phase_a.player_id)
    trigger = WorldLlmTurnTrigger(wiring=wiring)
    trigger._can_player_act = lambda pid: True  # type: ignore[method-assign]
    trigger.schedule_turn(PlayerId(1))
    trigger.schedule_turn(PlayerId(2))
    return trigger


def _skipped(recorder: CollectingTraceRecorder) -> list[tuple[str, object, int | None]]:
    return [
        (event.payload["stage"], event.payload["target_id"], event.tick)
        for event in recorder.of_kind(TraceEventKind.WORLD_TICK_UNIT_FAILED)
    ]


class TestIsolatePolicy:
    """isolate のとき、例外を出した 1 人のターンだけを取りやめ、他の人のターンは回ること。"""

    def test_serial_turn_failure_skips_only_that_player(self) -> None:
        """直列の経路で 1 人のターンが例外を出すと、その人だけを llm_turn として trace に残し、もう 1 人のターンは回る。ターンは CommandScope 1 回ではないので committed は分からない (None) と残す。"""
        recorder = CollectingTraceRecorder()
        trigger = _trigger(WorldTickFailurePolicy.ISOLATE, recorder, workers=0)

        trigger.run_scheduled_turns()

        assert trigger.wiring.run_turn.call_count == 2
        assert _skipped(recorder) == [("llm_turn", 1, 5)]
        assert recorder.events[0].payload["committed"] is None

    def test_parallel_phase_b_failure_skips_only_that_player(self) -> None:
        """並列の経路で 1 人の Phase B が例外を出すと、その人だけを trace に残し、もう 1 人の Phase B は回る。"""
        recorder = CollectingTraceRecorder()
        trigger = _trigger(WorldTickFailurePolicy.ISOLATE, recorder, workers=2)

        trigger.run_scheduled_turns()

        assert trigger.wiring.run_phase_b.call_count == 2
        assert _skipped(recorder) == [("llm_turn", 1, 5)]


class TestFailFastPolicy:
    """fail_fast のとき、1 人のターンの例外で止めること。"""

    def test_serial_turn_failure_stops_after_recording(self) -> None:
        """直列の経路で 1 人のターンが例外を出すと、trace に残したうえで例外を投げる。"""
        recorder = CollectingTraceRecorder()
        trigger = _trigger(WorldTickFailurePolicy.FAIL_FAST, recorder, workers=0)

        with pytest.raises(RuntimeError, match="prompt build failed"):
            trigger.run_scheduled_turns()

        assert _skipped(recorder) == [("llm_turn", 1, 5)]


class TestFollowUpFailures:
    """ターンの前後の判断や後処理の失敗を、続けたうえで trace に残すこと。"""

    def test_game_end_check_failure_is_recorded_and_turns_still_run(self) -> None:
        """isolate でゲーム終了の判定が例外を出すと、llm_turn.check_game_end として trace に残し、予定どおり全員のターンを回す。"""
        recorder = CollectingTraceRecorder()
        trigger = _trigger(WorldTickFailurePolicy.ISOLATE, recorder, workers=0)
        trigger.wiring.run_turn.side_effect = None
        trigger.wiring.run_turn.return_value = _OK
        trigger.wiring.runtime.check_game_end.side_effect = RuntimeError("registry broken")

        trigger.run_scheduled_turns()

        assert trigger.wiring.run_turn.call_count == 2
        failures = recorder.of_kind(TraceEventKind.WORLD_TICK_UNIT_FAILED)
        assert [(e.payload["stage"], e.payload["continued"]) for e in failures] == [
            ("llm_turn.check_game_end", True)
        ]
