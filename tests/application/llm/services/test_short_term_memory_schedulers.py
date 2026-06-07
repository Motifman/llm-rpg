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

    def test_submit_は_task_を_即時_実行する(self) -> None:
        called = []
        sch = InlineShortTermMemoryScheduler()
        accepted = sch.submit(player_id=1, task=lambda: called.append(True))
        assert accepted is True
        assert called == [True]

    def test_task_の例外は_scheduler_を_止めない(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
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

    def test_shutdown_は_no_op(self) -> None:
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

    def test_submit_は_別thread_で_task_を_実行する(self) -> None:
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

    def test_shutdown_は_in_flight_完了を_待つ(self) -> None:
        sch = ThreadPoolShortTermMemoryScheduler(max_workers=1)
        progress = {"done": False}

        def _slow() -> None:
            time.sleep(0.1)
            progress["done"] = True

        sch.submit(player_id=1, task=_slow)
        sch.shutdown()  # wait=True で完了待ち
        assert progress["done"] is True

    def test_shutdown_後の_submit_は_drop_して_warning_と_trace(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
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

    def test_queue_満杯時は_drop_して_trace(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
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

    def test_worker_の例外は_scheduler_を_止めない(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
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


class TestThreadPoolValidation:
    """constructor の不変条件。"""

    def test_max_workers_が_0以下なら_value_error(self) -> None:
        with pytest.raises(ValueError, match="max_workers"):
            ThreadPoolShortTermMemoryScheduler(max_workers=0)

    def test_max_queue_size_が_0以下なら_value_error(self) -> None:
        with pytest.raises(ValueError, match="max_queue_size"):
            ThreadPoolShortTermMemoryScheduler(max_queue_size=0)

    def test_trace_recorder_provider_が_非callable_なら_type_error(self) -> None:
        with pytest.raises(TypeError, match="trace_recorder_provider"):
            ThreadPoolShortTermMemoryScheduler(
                trace_recorder_provider="not-callable",  # type: ignore[arg-type]
            )
