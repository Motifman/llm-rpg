"""``InlineShortTermMemoryScheduler`` / ``ThreadPoolShortTermMemoryScheduler``
のテスト (Phase 2.1)。

- task が submit と同期 (Inline) / 非同期 (ThreadPool) で実行される
- queue 満杯 / shutdown 後の drop が trace + warning で観測可能
- task 内の例外は scheduler を停止させない
"""

from __future__ import annotations

import logging
import threading
import time
from typing import List

import pytest

from ai_rpg_world.application.llm.services.short_term_memory_schedulers import (
    InlineShortTermMemoryScheduler,
    ThreadPoolShortTermMemoryScheduler,
)
from ai_rpg_world.application.trace import (
    NullTraceRecorder,
    TraceEventKind,
)


# ──────────────────────────────────────────────────────────────────
# Inline
# ──────────────────────────────────────────────────────────────────


class TestInlineShortTermMemoryScheduler:
    """submit と同じ thread で task が即実行される。"""

    def test_submit_task_line(self) -> None:
        """submit は task を即時実行する。"""
        called = []
        sch = InlineShortTermMemoryScheduler()
        accepted = sch.submit(player_id=1, task=lambda: called.append(True))
        assert accepted is True
        assert called == [True]

    def test_task_scheduler_raises_exception(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """task の例外は scheduler を止めない。"""
        sch = InlineShortTermMemoryScheduler()

        def _raise() -> None:
            raise RuntimeError("oops")

        with caplog.at_level(
            logging.ERROR,
            logger="ai_rpg_world.application.llm.services.short_term_memory_schedulers",
        ):
            accepted = sch.submit(player_id=1, task=_raise)
        assert accepted is True
        # 後続 submit も動く
        called = []
        sch.submit(player_id=2, task=lambda: called.append(True))
        assert called == [True]
        assert any("task raised" in rec.message for rec in caplog.records)

    def test_task_trace_event_emit_raises_exception(self) -> None:
        """Phase 2.2: Inline でも task 例外で
        ``SHORT_TERM_SUMMARY_GENERATION_FAILED`` event を emit する。"""
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        sch = InlineShortTermMemoryScheduler(
            trace_recorder_provider=lambda: recorder,
            current_tick_provider=lambda: 42,
        )

        def _raise() -> None:
            raise ValueError("simulated parse failure")

        sch.submit(player_id=7, task=_raise)
        fails = [
            ev for ev in captured
            if ev.kind == TraceEventKind.SHORT_TERM_SUMMARY_GENERATION_FAILED
        ]
        assert len(fails) == 1
        assert fails[0].player_id == 7
        assert fails[0].tick == 42
        assert fails[0].payload["error_type"] == "ValueError"
        assert "simulated parse failure" in fails[0].payload["error_message_snippet"]
        assert "latency_ms" in fails[0].payload

    def test_trace_recorder_provider_unspecified_event_not_rendered(self) -> None:
        """trace 未配線でも例外時の動作自体は変わらない。"""
        sch = InlineShortTermMemoryScheduler()  # trace 無し

        def _raise() -> None:
            raise RuntimeError("x")

        # raises なし
        accepted = sch.submit(player_id=1, task=_raise)
        assert accepted is True

    def test_shutdown_op(self) -> None:
        """shutdown は no op。"""
        sch = InlineShortTermMemoryScheduler()
        sch.shutdown()  # raises なし
        sch.shutdown(timeout=1.0)


# ──────────────────────────────────────────────────────────────────
# ThreadPool
# ──────────────────────────────────────────────────────────────────


def _capture_trace(recorder: NullTraceRecorder) -> List:
    captured: List = []
    original = recorder.record

    def wrapper(kind, **kw):
        ev = original(kind, **kw)
        captured.append(ev)
        return ev

    recorder.record = wrapper  # type: ignore[method-assign]
    return captured


class TestThreadPoolShortTermMemoryScheduler:
    """ThreadPool で task が非同期実行される。"""

    def test_submit_different_thread_task_line(self) -> None:
        """submit は別 thread で task を実行する。"""
        sch = ThreadPoolShortTermMemoryScheduler(max_workers=1)
        try:
            done = threading.Event()
            tid_box: dict = {}

            def _task() -> None:
                tid_box["tid"] = threading.get_ident()
                done.set()

            accepted = sch.submit(player_id=1, task=_task)
            assert accepted is True
            assert done.wait(timeout=2.0), "task did not run within timeout"
            assert tid_box["tid"] != threading.get_ident()
        finally:
            sch.shutdown()

    def test_shutdown_flight(self) -> None:
        """shutdown は in flight 完了を 待つ。"""
        sch = ThreadPoolShortTermMemoryScheduler(max_workers=1)
        progress = {"done": False}

        def _slow() -> None:
            time.sleep(0.1)
            progress["done"] = True

        sch.submit(player_id=1, task=_slow)
        sch.shutdown()  # wait=True で完了待ち
        assert progress["done"] is True

    def test_emits_warning_for_shutdown_timeout(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """review MEDIUM #2: ThreadPoolExecutor.shutdown は timeout を取らないので
        サポートできない事実を warning で明示する。"""
        sch = ThreadPoolShortTermMemoryScheduler(max_workers=1)
        with caplog.at_level(
            logging.WARNING,
            logger="ai_rpg_world.application.llm.services.short_term_memory_schedulers",
        ):
            sch.shutdown(timeout=1.0)
        assert any("timeout" in rec.message for rec in caplog.records)

    def test_emits_warning_for_shutdown_submit_drop_trace(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """shutdown 後の submit は drop して warning と trace。"""
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        sch = ThreadPoolShortTermMemoryScheduler(
            max_workers=1,
            trace_recorder_provider=lambda: recorder,
        )
        sch.shutdown()
        with caplog.at_level(
            logging.WARNING,
            logger="ai_rpg_world.application.llm.services.short_term_memory_schedulers",
        ):
            accepted = sch.submit(player_id=7, task=lambda: None)
        assert accepted is False
        assert any("after shutdown" in rec.message for rec in caplog.records)
        drop_events = [
            ev for ev in captured if ev.kind == TraceEventKind.SHORT_TERM_SUMMARY_DROPPED
        ]
        assert len(drop_events) == 1
        assert drop_events[0].player_id == 7
        assert drop_events[0].payload["reason"] == "shutdown"

    def test_queue_drop_trace(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """queue 満杯時は drop して trace。"""
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        sch = ThreadPoolShortTermMemoryScheduler(
            max_workers=1,
            max_queue_size=1,
            trace_recorder_provider=lambda: recorder,
        )
        try:
            # worker が走り続けるよう、長めの task を仕込む
            block = threading.Event()
            release = threading.Event()

            def _blocking() -> None:
                block.set()
                release.wait(timeout=2.0)

            sch.submit(player_id=1, task=_blocking)
            assert block.wait(timeout=2.0)
            # ここから _blocking が走っているので in-flight=1
            # max_queue_size=1 で次は drop されるはず
            with caplog.at_level(
                logging.WARNING,
                logger="ai_rpg_world.application.llm.services.short_term_memory_schedulers",
            ):
                accepted = sch.submit(player_id=2, task=lambda: None)
            assert accepted is False
            assert any("キュー満杯" in rec.message for rec in caplog.records)
            drop_events = [
                ev for ev in captured
                if ev.kind == TraceEventKind.SHORT_TERM_SUMMARY_DROPPED
            ]
            assert len(drop_events) == 1
            assert drop_events[0].payload["reason"] == "queue_full"
        finally:
            release.set()
            sch.shutdown()

    def test_worker_scheduler_raises_exception(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """worker の例外は scheduler を止めない。"""
        sch = ThreadPoolShortTermMemoryScheduler(max_workers=1)
        try:
            done = threading.Event()

            def _raise() -> None:
                raise RuntimeError("oops")

            def _good() -> None:
                done.set()

            with caplog.at_level(
                logging.ERROR,
                logger="ai_rpg_world.application.llm.services.short_term_memory_schedulers",
            ):
                sch.submit(player_id=1, task=_raise)
                sch.submit(player_id=2, task=_good)
            assert done.wait(timeout=2.0)
            assert any("task failed" in rec.message for rec in caplog.records)
        finally:
            sch.shutdown()

    def test_worker_trace_event_emit_raises_exception(self) -> None:
        """Phase 2.2: ThreadPool でも worker 例外で
        ``SHORT_TERM_SUMMARY_GENERATION_FAILED`` event を emit する。"""
        recorder = NullTraceRecorder()
        captured = _capture_trace(recorder)
        sch = ThreadPoolShortTermMemoryScheduler(
            max_workers=1,
            trace_recorder_provider=lambda: recorder,
            current_tick_provider=lambda: 99,
        )
        try:
            done = threading.Event()

            def _raise() -> None:
                try:
                    raise ValueError("worker oops")
                finally:
                    done.set()

            sch.submit(player_id=3, task=_raise)
            assert done.wait(timeout=2.0)
        finally:
            sch.shutdown()  # in-flight 完了待ち
        fails = [
            ev for ev in captured
            if ev.kind == TraceEventKind.SHORT_TERM_SUMMARY_GENERATION_FAILED
        ]
        assert len(fails) == 1
        assert fails[0].player_id == 3
        assert fails[0].tick == 99
        assert fails[0].payload["error_type"] == "ValueError"
        assert "worker oops" in fails[0].payload["error_message_snippet"]


class TestThreadPoolValidation:
    """constructor の不変条件。"""

    def test_max_workers_zero_less_value_error(self) -> None:
        """max workers が 0以下なら value error。"""
        with pytest.raises(ValueError, match="max_workers"):
            ThreadPoolShortTermMemoryScheduler(max_workers=0)

    def test_max_queue_size_zero_less_value_error(self) -> None:
        """max queue size が 0以下なら value error。"""
        with pytest.raises(ValueError, match="max_queue_size"):
            ThreadPoolShortTermMemoryScheduler(max_queue_size=0)

    def test_trace_recorder_provider_non_callable_type_error_2(self) -> None:
        """tracerecorderprovider が非 callable なら typeerror。"""
        with pytest.raises(TypeError, match="trace_recorder_provider"):
            ThreadPoolShortTermMemoryScheduler(
                trace_recorder_provider="not-callable",  # type: ignore[arg-type]
            )

    def test_current_tick_provider_non_callable_type_error_2(self) -> None:
        """current_tick_provider に非callable を渡すと TypeError (Inline と対称)。"""
        with pytest.raises(TypeError, match="current_tick_provider"):
            ThreadPoolShortTermMemoryScheduler(
                current_tick_provider=42,  # type: ignore[arg-type]
            )


class TestInlineSchedulerValidation:
    """Phase 2.2: Inline scheduler の constructor 引数検証。"""

    def test_trace_recorder_provider_non_callable_type_error(self) -> None:
        """tracerecorderprovider が非 callable なら typeerror。"""
        with pytest.raises(TypeError, match="trace_recorder_provider"):
            InlineShortTermMemoryScheduler(
                trace_recorder_provider="not-callable",  # type: ignore[arg-type]
            )

    def test_current_tick_provider_non_callable_type_error(self) -> None:
        """currenttickprovider が非 callable なら typeerror。"""
        with pytest.raises(TypeError, match="current_tick_provider"):
            InlineShortTermMemoryScheduler(
                current_tick_provider=42,  # type: ignore[arg-type]
            )
