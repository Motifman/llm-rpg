"""outbox定期配送がサーバ処理を止めず、失敗後も再試行する契約を保証する。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import threading
import time

import pytest

from ai_rpg_world.application.common.outbox_worker import OutboxRunResult
from ai_rpg_world.presentation.spot_graph_game.outbox_delivery_loop import (
    OutboxDeliveryLoop,
)


@dataclass
class _RecordingWorker:
    """呼出し回数・引数・実行スレッドを記録するworker代役。"""

    errors: list[Exception] = field(default_factory=list)
    calls: list[int] = field(default_factory=list)
    thread_ids: list[int] = field(default_factory=list)

    def run_once(self, *, limit: int = 100) -> OutboxRunResult:
        self.calls.append(limit)
        self.thread_ids.append(threading.get_ident())
        if self.errors:
            raise self.errors.pop(0)
        return OutboxRunResult(delivered_count=0, rejected_count=0)


@dataclass
class _BlockingWorker:
    """releaseされるまで最初のworker実行を止める代役。"""

    entered: threading.Event = field(default_factory=threading.Event)
    release: threading.Event = field(default_factory=threading.Event)
    calls: int = 0

    def run_once(self, *, limit: int = 100) -> OutboxRunResult:
        self.calls += 1
        self.entered.set()
        if self.calls == 1:
            self.release.wait(timeout=2.0)
        return OutboxRunResult(delivered_count=0, rejected_count=0)


async def _wait_until(predicate, *, timeout: float = 2.0) -> bool:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        if predicate():
            return True
        await asyncio.sleep(0.005)
    return predicate()


class TestOutboxDeliveryLoop:
    """単一プロセス用outbox loopの周期・停止・障害分離を保証する。"""

    def test_runs_immediately_and_repeats_with_bounded_batch(self) -> None:
        """start直後と各間隔後に、指定した最大件数でworkerを呼ぶ。"""
        worker = _RecordingWorker()

        async def scenario() -> bool:
            loop = OutboxDeliveryLoop(
                worker=worker,
                interval_seconds=0.02,
                batch_limit=7,
            )
            loop.start()
            try:
                return await _wait_until(lambda: len(worker.calls) >= 2)
            finally:
                await loop.stop()

        assert asyncio.run(scenario()) is True
        assert worker.calls[:2] == [7, 7]

    def test_failure_is_logged_and_next_interval_retries(
        self,
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        """1回の配送失敗はloopを終了させず、次の周期で再試行する。"""
        worker = _RecordingWorker(errors=[RuntimeError("temporary")])

        async def scenario() -> bool:
            loop = OutboxDeliveryLoop(
                worker=worker,
                interval_seconds=0.02,
            )
            loop.start()
            try:
                return await _wait_until(lambda: len(worker.calls) >= 2)
            finally:
                await loop.stop()

        with caplog.at_level("WARNING"):
            assert asyncio.run(scenario()) is True

        assert "outboxの定期再配送に失敗" in caplog.text

    def test_worker_runs_outside_event_loop_thread(self) -> None:
        """同期SQLite処理を想定したworkerはasyncio event loopと別threadで実行する。"""
        worker = _RecordingWorker()

        async def scenario() -> tuple[int, bool]:
            event_loop_thread_id = threading.get_ident()
            loop = OutboxDeliveryLoop(
                worker=worker,
                interval_seconds=1.0,
            )
            loop.start()
            try:
                called = await _wait_until(lambda: bool(worker.calls))
                return event_loop_thread_id, called
            finally:
                await loop.stop()

        event_loop_thread_id, called = asyncio.run(scenario())
        assert called is True
        assert worker.thread_ids[0] != event_loop_thread_id

    def test_start_and_stop_are_idempotent(self) -> None:
        """start/stopを重複して呼んでもtaskを多重生成せず安全に終了する。"""
        worker = _RecordingWorker()

        async def scenario() -> OutboxDeliveryLoop:
            loop = OutboxDeliveryLoop(worker=worker, interval_seconds=1.0)
            loop.start()
            first_task = loop._task
            loop.start()
            assert loop._task is first_task
            await _wait_until(lambda: bool(worker.calls))
            await loop.stop()
            await loop.stop()
            return loop

        loop = asyncio.run(scenario())
        assert loop.is_running is False
        assert worker.calls == [100]

    def test_stop_does_not_start_another_delivery(self) -> None:
        """stop完了後は間隔が経過しても新しいworker実行を開始しない。"""
        worker = _RecordingWorker()

        async def scenario() -> tuple[int, int]:
            loop = OutboxDeliveryLoop(worker=worker, interval_seconds=0.02)
            loop.start()
            await _wait_until(lambda: bool(worker.calls))
            await loop.stop()
            calls_at_stop = len(worker.calls)
            await asyncio.sleep(0.05)
            return calls_at_stop, len(worker.calls)

        calls_at_stop, calls_later = asyncio.run(scenario())
        assert calls_later == calls_at_stop

    def test_restart_skips_until_cancelled_executor_work_finishes(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """停止猶予を超えた旧workerが残っても、再startしたworkerと重複しない。"""
        import ai_rpg_world.presentation.spot_graph_game.outbox_delivery_loop as module

        monkeypatch.setattr(module, "_STOP_GRACE_SECONDS", 0.01)
        worker = _BlockingWorker()

        async def scenario() -> tuple[int, int]:
            loop = OutboxDeliveryLoop(worker=worker, interval_seconds=0.01)
            loop.start()
            await _wait_until(worker.entered.is_set)
            await loop.stop()
            loop.start()
            await asyncio.sleep(0.05)
            calls_while_old_worker_runs = worker.calls
            worker.release.set()
            await _wait_until(lambda: worker.calls >= 2)
            await loop.stop()
            return calls_while_old_worker_runs, worker.calls

        calls_while_old_worker_runs, final_calls = asyncio.run(scenario())
        assert calls_while_old_worker_runs == 1
        assert final_calls >= 2

    def test_second_stop_cancels_restart_without_queued_delivery(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """旧worker実行中の再startをstopすると、旧worker終了後も配送を始めない。"""
        import ai_rpg_world.presentation.spot_graph_game.outbox_delivery_loop as module

        monkeypatch.setattr(module, "_STOP_GRACE_SECONDS", 0.01)
        worker = _BlockingWorker()

        async def scenario() -> tuple[int, int]:
            loop = OutboxDeliveryLoop(worker=worker, interval_seconds=0.01)
            loop.start()
            await _wait_until(worker.entered.is_set)
            await loop.stop()

            loop.start()
            await asyncio.sleep(0.03)
            await loop.stop()
            calls_after_both_stops = worker.calls

            worker.release.set()
            await asyncio.sleep(0.05)
            return calls_after_both_stops, worker.calls

        calls_after_both_stops, calls_after_release = asyncio.run(scenario())
        assert calls_after_both_stops == 1
        assert calls_after_release == 1

    @pytest.mark.parametrize(
        ("interval_seconds", "batch_limit"),
        (
            (0.0, 100),
            (float("nan"), 100),
            (float("inf"), 100),
            (True, 100),
            (1.0, 0),
            (1.0, True),
        ),
    )
    def test_invalid_settings_are_rejected(
        self,
        interval_seconds: float,
        batch_limit: int,
    ) -> None:
        """過密周期や無効な最大件数はbusy loopを作る前に拒否する。"""
        with pytest.raises(ValueError):
            OutboxDeliveryLoop(
                worker=_RecordingWorker(),
                interval_seconds=interval_seconds,
                batch_limit=batch_limit,
            )
