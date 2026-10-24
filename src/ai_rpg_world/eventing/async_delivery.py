"""本人ごとに受け手を直列実行し、結果の反映を呼び出す側へ戻す。"""

from __future__ import annotations

import logging
import math
from collections import defaultdict, deque
from collections.abc import Callable, Hashable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from threading import RLock
from typing import Any, Generic, Literal, TypeVar

from ai_rpg_world.eventing.domain_event import DomainEvent

_Event = TypeVar("_Event", bound=DomainEvent)
_Result = TypeVar("_Result")


@dataclass(frozen=True)
class AsyncFailure:
    """実行や反映の失敗と、受付拒否・終了期限による破棄を知らせる。"""

    reason: Literal["handler_failed", "capacity", "shutdown", "shutdown_timeout", "application_failed"]
    key: Hashable
    event: DomainEvent
    handler: object
    error: BaseException | None = None


@dataclass(frozen=True)
class _Work:
    key: Hashable
    event: DomainEvent
    handler: Callable[[Any], Any]
    apply_result: Callable[[Any], None]


class AsyncEventExecutor:
    """未反映の件数を制限し、同じ宛先の受け手を到着順に呼ぶ。"""

    def __init__(
        self, *, failure_observer: Callable[[AsyncFailure], None], max_workers: int = 2, max_pending: int = 100,
    ) -> None:
        if not callable(failure_observer):
            raise TypeError("failure_observerは呼び出せる必要があります")
        for name, value in (("max_workers", max_workers), ("max_pending", max_pending)):
            if isinstance(value, bool) or not isinstance(value, int) or value < 1:
                raise ValueError(f"{name}は1以上の整数である必要があります")
        self._observer = failure_observer
        self._max_pending = max_pending
        self._pool = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="eventing")
        self._lock = RLock()
        self._futures: set[Future[None]] = set()
        self._queues: dict[Hashable, deque[int]] = {}
        self._unfinished: dict[int, _Work] = {}
        self._ready: dict[Hashable, deque[tuple[_Work, Any]]] = defaultdict(deque)
        self._applying = 0
        self._sequence = 0
        self._accepting = True
        self._closed = False

    @property
    def pending_count(self) -> int:
        """実行待ち・実行中・反映待ちを合わせた件数を返す。"""
        with self._lock:
            return self._applying + len(self._unfinished) + sum(len(queue) for queue in self._ready.values())

    def submit(
        self, *, key: Hashable, event: _Event, handler: Callable[[_Event], _Result],
        apply_result: Callable[[_Result], None],
    ) -> bool:
        """受付の可否を返し、実行の完了は待たない。"""
        hash(key)
        work = _Work(key, event, handler, apply_result)
        with self._lock:
            if not self._accepting:
                self._notify(AsyncFailure("shutdown", key, event, handler))
                return False
            if self.pending_count >= self._max_pending:
                self._notify(AsyncFailure("capacity", key, event, handler))
                return False
            self._sequence += 1
            number = self._sequence
            self._unfinished[number] = work
            if key in self._queues:
                self._queues[key].append(number)
            else:
                self._queues[key] = deque([number])
                future = self._pool.submit(self._run_recipient, key)
                self._futures.add(future)
                future.add_done_callback(self._finished)
            return True

    def _finished(self, future: Future[None]) -> None:
        with self._lock:
            self._futures.discard(future)

    def _run_recipient(self, key: Hashable) -> None:
        while True:
            with self._lock:
                queue = self._queues.get(key)
                if not queue:
                    self._queues.pop(key, None)
                    return
                number = queue.popleft()
                work = self._unfinished[number]
            try:
                result = work.handler(work.event)
            except BaseException as error:
                with self._lock:
                    if self._unfinished.pop(number, None) is not None:
                        self._notify(AsyncFailure("handler_failed", key, work.event, work.handler, error))
            else:
                with self._lock:
                    if self._unfinished.pop(number, None) is not None:
                        self._ready[key].append((work, result))

    def apply_results(self, key: Hashable) -> None:
        """本人の完了した結果だけを、呼び出したスレッドで反映する。"""
        while True:
            with self._lock:
                queue = self._ready.get(key)
                if not queue:
                    self._ready.pop(key, None)
                    return
                work, result = queue.popleft()
                self._applying += 1
            try:
                work.apply_result(result)
            except Exception as error:
                self._notify(AsyncFailure("application_failed", key, work.event, work.handler, error))
                raise
            finally:
                with self._lock:
                    self._applying -= 1

    def apply_all_results(self) -> None:
        """終了時に、完了した全員の結果を呼び出したスレッドで反映する。"""
        with self._lock:
            keys = tuple(self._ready)
        for key in keys:
            self.apply_results(key)

    def shutdown(self, *, timeout: float = 10.0) -> None:
        """受付を止めて期限まで待ち、残った仕事を破棄として知らせる。反映待ちは残す。"""
        if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout < 0:
            raise ValueError("timeoutは0以上の有限の秒数である必要があります")
        with self._lock:
            if self._closed:
                return
            self._accepting = False
            futures = tuple(self._futures)
        wait(futures, timeout=timeout)
        with self._lock:
            self._closed = True
            abandoned = tuple(self._unfinished.values())
            self._unfinished.clear()
            self._queues.clear()
            for work in abandoned:
                self._notify(AsyncFailure("shutdown_timeout", work.key, work.event, work.handler))
        # 実行中の Python スレッドは止められない。遅れて返った結果は上の表に無いので捨てる。
        self._pool.shutdown(wait=False, cancel_futures=True)

    def _notify(self, failure: AsyncFailure) -> None:
        try:
            self._observer(failure)
        except Exception:
            logging.getLogger(__name__).exception("非同期の受け手の失敗を知らせられませんでした")


@dataclass(frozen=True)
class AsyncDelivery(Generic[_Event, _Result]):
    """宛先の取り出し方と結果の反映先を、非同期の受け手に結び付ける。"""

    executor: AsyncEventExecutor
    recipient_key: Callable[[_Event], Hashable]
    apply_result: Callable[[_Result], None]

    def bind(self, handler: Callable[[_Event], _Result]) -> Callable[[_Event], None]:
        """共通の配送器に、完了を待たず受付へ渡す受け手を返す。"""
        def enqueue(event: _Event) -> None:
            self.executor.submit(
                key=self.recipient_key(event), event=event, handler=handler, apply_result=self.apply_result
            )
        return enqueue
