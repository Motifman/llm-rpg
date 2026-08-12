"""シナリオ述語traceが公開runtime入口まで遅延配線されることを保証する。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ai_rpg_world.application.trace import NullTraceRecorder, TraceEvent, TraceEventKind
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)


_SCENARIO = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "scenarios"
    / "survival_island_v4_coop.json"
)


class _CollectingRecorder(NullTraceRecorder):
    """NullTraceRecorderの採番を使いながら記録結果を保持する。"""

    def __init__(self) -> None:
        super().__init__()
        self.events = []

    def record(
        self,
        kind: str,
        *,
        tick: Optional[int] = None,
        player_id: Optional[int] = None,
        **payload: Any,
    ) -> TraceEvent:
        event = super().record(
            kind,
            tick=tick,
            player_id=player_id,
            **payload,
        )
        self.events.append(event)
        return event


class TestScenarioPredicateTraceWiring:
    """構築後に設定した記録器へ、実tickの述語評価を届ける。"""

    def test_late_trace_recorder_receives_actual_stage_evaluations(self) -> None:
        """runtime構築後のset_trace_recorderでも、advance_tickの各評価が記録される。"""
        runtime = create_world_runtime(
            _SCENARIO,
            config=ResolvedLlmRuntimeConfig.for_tests(scenario_random_seed=1046),
        )
        recorder = _CollectingRecorder()
        runtime.set_trace_recorder(recorder)

        runtime.advance_tick()

        predicate_events = [
            event
            for event in recorder.events
            if event.kind == TraceEventKind.SCENARIO_PREDICATE_EVALUATED
        ]
        assert predicate_events
        assert {
            event.payload["purpose"] for event in predicate_events
        } >= {
            "scenario_event_conditions",
            "reactive_object_binding",
            "reactive_passage_binding",
            "player_outcome_trigger",
        }
        assert all(
            "probability_decisions" in event.payload
            for event in predicate_events
        )
