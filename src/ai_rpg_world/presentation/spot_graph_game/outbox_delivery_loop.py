"""FastAPIの生存期間で単一outbox workerを定期実行する駆動処理。"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass, field
import logging
import math
from threading import Lock
from typing import Optional, Protocol

from ai_rpg_world.application.common.outbox_worker import OutboxRunResult


logger = logging.getLogger(__name__)

_MIN_INTERVAL_SECONDS = 0.01
_STOP_GRACE_SECONDS = 2.0


class OutboxWorkerPort(Protocol):
    """定期駆動に必要なoutbox workerの最小契約。"""

    def run_once(self, *, limit: int = 100) -> OutboxRunResult: ...


@dataclass
class OutboxDeliveryLoop:
    """単一プロセス内でoutboxの有界な再配送を直列実行する。"""

    worker: OutboxWorkerPort
    interval_seconds: float = 1.0
    batch_limit: int = 100
    _task: Optional[asyncio.Task[None]] = field(default=None, init=False, repr=False)
    _stop_event: Optional[asyncio.Event] = field(
        default=None,
        init=False,
        repr=False,
    )
    _worker_lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __post_init__(self) -> None:
        if (
            isinstance(self.interval_seconds, bool)
            or not isinstance(self.interval_seconds, (int, float))
            or not math.isfinite(self.interval_seconds)
            or self.interval_seconds < _MIN_INTERVAL_SECONDS
        ):
            raise ValueError(
                f"interval_secondsは{_MIN_INTERVAL_SECONDS}以上である必要があります"
            )
        if (
            isinstance(self.batch_limit, bool)
            or not isinstance(self.batch_limit, int)
            or self.batch_limit < 1
        ):
            raise ValueError("batch_limitは1以上の整数である必要があります")

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """loopを一度だけ開始する。既に実行中なら何もしない。"""
        if self.is_running:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(
            self._run(),
            name="outbox_delivery_loop",
        )

    async def stop(self) -> None:
        """停止を通知し、実行中の1回が終了するまで待つ。"""
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is None:
            return
        try:
            await asyncio.wait_for(
                self._task,
                timeout=self.interval_seconds + _STOP_GRACE_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("outbox定期配送が猶予時間内に停止しないためtaskを取消します")
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        finally:
            self._task = None
            self._stop_event = None

    async def _run(self) -> None:
        stop_event = self._stop_event
        if stop_event is None:
            raise RuntimeError("start()を介さずoutbox loopを実行できません")
        event_loop = asyncio.get_running_loop()
        logger.info(
            "outbox定期配送を開始しました: interval=%.3fs batch_limit=%d",
            self.interval_seconds,
            self.batch_limit,
        )
        try:
            while not stop_event.is_set():
                try:
                    result = await event_loop.run_in_executor(
                        None,
                        self._run_worker_once,
                    )
                    if result.dead_lettered_count:
                        logger.warning(
                            "outboxイベントをdead letterへ隔離しました: count=%d",
                            result.dead_lettered_count,
                        )
                    if result.delivered_count or result.rejected_count:
                        logger.info(
                            "outbox定期配送が完了しました: delivered=%d rejected=%d",
                            result.delivered_count,
                            result.rejected_count,
                        )
                except Exception as error:
                    dead_lettered_count = getattr(
                        error,
                        "dead_lettered_count",
                        0,
                    )
                    if dead_lettered_count:
                        logger.warning(
                            "outboxイベントをdead letterへ隔離しました: count=%d",
                            dead_lettered_count,
                        )
                    logger.warning(
                        "outboxの定期再配送に失敗しました。次の周期で再試行します",
                        exc_info=True,
                    )
                try:
                    await asyncio.wait_for(
                        stop_event.wait(),
                        timeout=self.interval_seconds,
                    )
                except asyncio.TimeoutError:
                    continue
        finally:
            logger.info("outbox定期配送を停止しました")

    def _run_worker_once(self) -> OutboxRunResult:
        # asyncio taskを取消してもexecutor内の同期処理は止まらない。
        # lock待ちの仕事も取消不能なので、旧実行が残る場合は待たずに
        # この周期をskipし、stop後に遅れて配送が始まるのを防ぐ。
        if not self._worker_lock.acquire(blocking=False):
            return OutboxRunResult(delivered_count=0, rejected_count=0)
        try:
            return self.worker.run_once(limit=self.batch_limit)
        finally:
            self._worker_lock.release()


__all__ = ["OutboxDeliveryLoop", "OutboxWorkerPort"]
