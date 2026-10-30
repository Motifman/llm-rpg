"""SpotGraphSimulationApplicationService が段と確定後フックの例外を、方針に従って取りやめるか止めるかを保証する。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from ai_rpg_world.application.common.exceptions import SystemErrorException
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.application.trace.recorder import NullTraceRecorder
from ai_rpg_world.application.world_graph.exceptions import SpotGraphPostTickHookFailedException
from ai_rpg_world.application.world_graph.spot_graph_simulation_application_service import (
    SpotGraphSimulationApplicationService,
)
from ai_rpg_world.application.world_graph.world_tick_failure_isolation import (
    WorldTickFailureIsolator,
    WorldTickFailurePolicy,
)
from ai_rpg_world.domain.common.value_object import WorldTick
from ai_rpg_world.infrastructure.services.in_memory_game_time_provider import (
    InMemoryGameTimeProvider,
)


class _CollectingRecorder(NullTraceRecorder):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[Any] = []

    def record(self, kind: str, **kwargs: Any) -> Any:
        event = super().record(kind, **kwargs)
        self.events.append(event)
        return event


@dataclass
class _Stage:
    name: str
    calls: list[str]
    fails: bool = False

    def run(self, current_tick: WorldTick) -> None:
        self.calls.append(self.name)
        if self.fails:
            raise RuntimeError(f"{self.name} failed")


@dataclass
class _Trigger:
    calls: list[str]
    fails: bool = False

    def schedule_turn(self, player_id: Any) -> None:
        pass

    def run_scheduled_turns(self) -> None:
        self.calls.append("llm_turn_trigger")
        if self.fails:
            raise RuntimeError("turn failed")


def _isolator(policy: WorldTickFailurePolicy, recorder: Any) -> WorldTickFailureIsolator:
    return WorldTickFailureIsolator(policy=policy, trace_recorder_provider=lambda: recorder)


class TestIsolatePolicy:
    """isolate のとき、例外を出した段やフックだけを取りやめ、tick の残りを進めること。"""

    def test_failing_stage_is_skipped_and_later_stages_and_hooks_still_run(self) -> None:
        """isolate で段が例外を出すと、tick は止まらず後段と確定後フックが走り、段を対象にした world_tick_unit_failed が残る。"""
        calls: list[str] = []
        recorder = _CollectingRecorder()
        service = SpotGraphSimulationApplicationService(
            time_provider=InMemoryGameTimeProvider(),
            travel_stage=_Stage("travel", calls, fails=True),
            scenario_event_stage=_Stage("scenario_event", calls),
            llm_turn_trigger=_Trigger(calls),
            failure_isolator=_isolator(WorldTickFailurePolicy.ISOLATE, recorder),
        )

        tick = service.tick()

        assert calls == ["travel", "scenario_event", "llm_turn_trigger"]
        assert [e.kind for e in recorder.events] == [TraceEventKind.WORLD_TICK_UNIT_FAILED]
        assert recorder.events[0].tick == tick.value
        assert recorder.events[0].payload["stage"] == "travel"
        assert recorder.events[0].payload["target_kind"] == "stage"

    def test_failing_post_tick_hook_is_recorded_without_raising(self) -> None:
        """isolate で確定後フックが例外を出すと、例外は外へ出ず post_tick.<名前> の段として残る。"""
        calls: list[str] = []
        recorder = _CollectingRecorder()
        service = SpotGraphSimulationApplicationService(
            time_provider=InMemoryGameTimeProvider(),
            llm_turn_trigger=_Trigger(calls, fails=True),
            failure_isolator=_isolator(WorldTickFailurePolicy.ISOLATE, recorder),
        )

        service.tick()

        assert recorder.events[0].payload["stage"] == "post_tick.llm_turn_trigger"
        assert recorder.events[0].payload["target_kind"] == "post_tick_hook"


class TestFailFastPolicy:
    """fail_fast のとき、これまでどおり例外で tick を止めること。"""

    def test_failing_stage_stops_the_tick_after_recording(self) -> None:
        """fail_fast で段が例外を出すと、world_tick_unit_failed を残したうえで tick を止め、後段は走らない。"""
        calls: list[str] = []
        recorder = _CollectingRecorder()
        service = SpotGraphSimulationApplicationService(
            time_provider=InMemoryGameTimeProvider(),
            travel_stage=_Stage("travel", calls, fails=True),
            scenario_event_stage=_Stage("scenario_event", calls),
            failure_isolator=_isolator(WorldTickFailurePolicy.FAIL_FAST, recorder),
        )

        with pytest.raises(SystemErrorException):
            service.tick()

        assert calls == ["travel"]
        assert recorder.events[0].payload["stage"] == "travel"

    def test_without_isolator_stage_failure_stops_the_tick(self) -> None:
        """取りやめの部品を渡さなければ fail_fast と同じく、段の例外で tick を止める。"""
        calls: list[str] = []
        service = SpotGraphSimulationApplicationService(
            time_provider=InMemoryGameTimeProvider(),
            travel_stage=_Stage("travel", calls, fails=True),
            scenario_event_stage=_Stage("scenario_event", calls),
        )

        with pytest.raises(SystemErrorException):
            service.tick()

        assert calls == ["travel"]

    def test_failing_post_tick_hook_runs_remaining_hooks_then_raises(self) -> None:
        """fail_fast で確定後フックが例外を出しても残りのフックは走り、最後にまとめて投げる。"""
        calls: list[str] = []
        recorder = _CollectingRecorder()
        service = SpotGraphSimulationApplicationService(
            time_provider=InMemoryGameTimeProvider(),
            graph_event_flusher=lambda: (_ for _ in ()).throw(RuntimeError("flush failed")),
            llm_turn_trigger=_Trigger(calls),
            failure_isolator=_isolator(WorldTickFailurePolicy.FAIL_FAST, recorder),
        )

        with pytest.raises(SpotGraphPostTickHookFailedException):
            service.tick()

        assert calls == ["llm_turn_trigger"]
        assert recorder.events[0].payload["stage"] == "post_tick.graph_event_flusher"
