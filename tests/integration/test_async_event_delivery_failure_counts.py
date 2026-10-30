"""本番の runtime が、非同期のハンドラの失敗を trace に残すたびに理由ごとに数えることを保証する (design_decisions D1824-16)。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from ai_rpg_world.application.llm.wiring.resolved_runtime_config import ResolvedLlmRuntimeConfig
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.world_runtime.world_runtime import create_world_runtime
from ai_rpg_world.eventing import AsyncFailure, DomainEvent
from tests.trace_helpers import RecordingTraceRecorder

_ISLAND = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "survival_island_v4_coop.json"


def _failure(reason: str) -> AsyncFailure:
    return AsyncFailure(reason, "being_p1", DomainEvent(1, datetime.now(timezone.utc)), object(), RuntimeError("失敗"))  # type: ignore[arg-type]


class TestAsyncEventDeliveryFailureCounts:
    """WorldRuntime.async_event_delivery_failure_counts が、知らされた失敗を理由ごとに数えることを保証する。"""

    def test_failures_are_counted_by_reason_and_traced(self) -> None:
        """知らされた失敗を理由ごとに数え、1 件ごとに async_event_delivery_failed を残す。失敗の無い run は空の件数を返す。"""
        runtime = create_world_runtime(_ISLAND, config=ResolvedLlmRuntimeConfig.for_tests())
        recorder = RecordingTraceRecorder()
        runtime.set_trace_recorder(recorder)
        assert runtime.async_event_delivery_failure_counts() == {}

        for reason in ("handler_failed", "handler_failed", "capacity"):
            runtime._record_async_delivery_failure(_failure(reason))

        assert runtime.async_event_delivery_failure_counts() == {"handler_failed": 2, "capacity": 1}
        assert len(recorder.payloads(TraceEventKind.ASYNC_EVENT_DELIVERY_FAILED)) == 3

    def test_failure_without_recorder_is_still_counted(self) -> None:
        """trace の recorder が無くて記録で例外になっても、件数には入る。"""
        runtime = create_world_runtime(_ISLAND, config=ResolvedLlmRuntimeConfig.for_tests())
        runtime.set_trace_recorder(None)

        with pytest.raises(RuntimeError):
            runtime._record_async_delivery_failure(_failure("prepare_failed"))

        assert runtime.async_event_delivery_failure_counts() == {"prepare_failed": 1}

    def test_failures_from_the_executor_are_counted(self) -> None:
        """runtime の AsyncEventExecutor に失敗する仕事を渡すと、別のスレッドで失敗した件数がすべて handler_failed として数えられる。"""
        runtime = create_world_runtime(_ISLAND, config=ResolvedLlmRuntimeConfig.for_tests())
        runtime.set_trace_recorder(RecordingTraceRecorder())

        def broken(event: DomainEvent) -> None:
            raise RuntimeError("失敗")

        for number in range(20):
            runtime.async_event_executor.submit(
                key=f"being_p{number % 4}",
                event=DomainEvent(number, datetime.now(timezone.utc)),
                handler=broken,
                apply_result=lambda result: None,
            )
        runtime.async_event_executor.shutdown(timeout=5)

        assert runtime.async_event_delivery_failure_counts() == {"handler_failed": 20}
