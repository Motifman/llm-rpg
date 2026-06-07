"""``RollingSummaryShortTermMemory`` の L4 生成タスクを実行する scheduler。

Phase 2.1 (#356 後続): L4 生成 (LLM 2-5s) を inline (sync) と非同期
(ThreadPool) のどちらで実行するかを差し替えられるようにする。

設計指針:

- **task は callable**: ``submit(player_id, task)``。RollingSummary 側は
  L1 から observations を pop した後、LLM 呼出 + L4 install をクロージャ
  化して投げる。scheduler は実行戦略 (今 or 裏) だけを担う
- **Inline**: 互換性のため既存挙動 (submit と同じ thread で task 実行) を維持
- **ThreadPool**: ``concurrent.futures.ThreadPoolExecutor`` で非同期化。
  キュー満杯時は ``SHORT_TERM_SUMMARY_DROPPED`` trace を吐いて drop
  (silent failure 防止)
- **shutdown**: ThreadPool は graceful shutdown を提供 (in-flight 完了待ち)

既存 ``EpisodicChunkSubjectiveScheduler`` の pattern を踏襲しているが、
本 scheduler は task を opaque な callable として扱うのでより汎用。

詳細: docs/memory_system/short_term_memory_design.md §6 (Phase 2.1 後続)。
"""

from __future__ import annotations

import logging
import threading
import time
from abc import ABC, abstractmethod
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Callable, Optional

from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind


_logger = logging.getLogger(__name__)


# L4 生成タスクの型。引数なしで実行され、副作用 (L4 install) を行う。
L4GenerationTask = Callable[[], None]


class IShortTermMemoryScheduler(ABC):
    """L4 生成タスクの実行戦略を抽象化する。"""

    @abstractmethod
    def submit(self, player_id: int, task: L4GenerationTask) -> bool:
        """task を実行する。

        Returns:
            True なら受理した (即時 or 後刻に実行される)、False なら drop。
        """
        raise NotImplementedError

    @abstractmethod
    def shutdown(self, timeout: Optional[float] = None) -> None:
        """完了待ち + 終了。Inline は no-op、ThreadPool は executor を閉じる。"""
        raise NotImplementedError


class InlineShortTermMemoryScheduler(IShortTermMemoryScheduler):
    """submit と同じ thread で即時 task を実行する scheduler (同期)。

    Phase 2 の MVP 挙動と互換。テスト / オフライン / 同期保証が必要なときに使う。
    """

    def submit(self, player_id: int, task: L4GenerationTask) -> bool:
        # 通常 task (= ``RollingSummaryShortTermMemory._run_generation``) は
        # 内部で全例外を握って template fallback を install するため、ここに
        # 到達するのは task 内のバグ時のみ。その場合でも scheduler 自体は
        # 止めず、warning ログを残して True を返す (受理は成功、実行は失敗)。
        # 呼出側は True を「L4 が install される」と期待しているため、本当に
        # install を保証したい場合は task 側で fallback を確実にすること。
        try:
            task()
        except Exception:
            _logger.exception(
                "InlineShortTermMemoryScheduler: task raised for player_id=%s",
                player_id,
            )
        return True

    def shutdown(self, timeout: Optional[float] = None) -> None:
        del timeout


class ThreadPoolShortTermMemoryScheduler(IShortTermMemoryScheduler):
    """``ThreadPoolExecutor`` で task を非同期実行する scheduler。

    LLM 呼び出しは I/O bound (HTTP 待ち) なので GIL は実害が無い。
    in-flight 件数が ``max_queue_size`` に達した状態で新規 submit すると drop
    + trace 出力する。

    Args:
        max_workers: ワーカー thread 数 (既定 1)。LLM API の RPS 制限を考慮
            すると 1〜2 が安全側
        max_queue_size: in-flight + pending の上限。これを超えると drop
        trace_recorder_provider / current_tick_provider: 任意の trace 配線
    """

    def __init__(
        self,
        *,
        max_workers: int = 1,
        max_queue_size: int = 100,
        trace_recorder_provider: Optional[Callable[[], Optional[ITraceRecorder]]] = None,
        current_tick_provider: Optional[Callable[[], Optional[int]]] = None,
    ) -> None:
        if not isinstance(max_workers, int) or max_workers < 1:
            raise ValueError("max_workers must be a positive int")
        if not isinstance(max_queue_size, int) or max_queue_size < 1:
            raise ValueError("max_queue_size must be a positive int")
        if trace_recorder_provider is not None and not callable(trace_recorder_provider):
            raise TypeError("trace_recorder_provider must be callable or None")
        if current_tick_provider is not None and not callable(current_tick_provider):
            raise TypeError("current_tick_provider must be callable or None")
        self._max_queue_size = max_queue_size
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="st_summary",
        )
        self._inflight_lock = threading.Lock()
        self._inflight: set[Future] = set()
        self._is_shutdown = False

    def submit(self, player_id: int, task: L4GenerationTask) -> bool:
        # shutdown / 満杯チェックは lock 内で原子的に
        with self._inflight_lock:
            if self._is_shutdown:
                _logger.warning(
                    "ThreadPoolShortTermMemoryScheduler.submit called after "
                    "shutdown; dropping task for player_id=%s",
                    player_id,
                )
                self._emit_drop(player_id, reason="shutdown", queue_size=0)
                return False
            current = len(self._inflight)
            if current >= self._max_queue_size:
                _logger.warning(
                    "ThreadPoolShortTermMemoryScheduler: キュー満杯 (%d/%d)、"
                    "新規 task を drop: player_id=%s",
                    current,
                    self._max_queue_size,
                    player_id,
                )
                self._emit_drop(
                    player_id, reason="queue_full", queue_size=current
                )
                return False
        # ロック外で executor.submit (デッドロック回避)
        try:
            future = self._executor.submit(self._worker, player_id, task)
        except RuntimeError:
            _logger.warning(
                "ThreadPoolShortTermMemoryScheduler: executor already shutdown; "
                "dropping task for player_id=%s",
                player_id,
                exc_info=True,
            )
            self._emit_drop(player_id, reason="executor_shutdown", queue_size=0)
            return False
        with self._inflight_lock:
            self._inflight.add(future)
        future.add_done_callback(lambda f: self._on_done(f))
        return True

    def shutdown(self, timeout: Optional[float] = None) -> None:
        """in-flight 完了を待って executor を閉じる。

        現実装の制約: Python 3.10 の ``ThreadPoolExecutor.shutdown`` は
        ``timeout`` を取らず、また実行中タスクの強制中断手段もない。
        ``timeout`` を渡された場合は warning を出すだけで実質的な打ち切り
        制御は行わない (review MEDIUM #2)。
        """
        if timeout is not None:
            _logger.warning(
                "ThreadPoolShortTermMemoryScheduler.shutdown: timeout=%s は "
                "現実装ではサポートされていません。in-flight 完了まで待ちます。",
                timeout,
            )
        with self._inflight_lock:
            self._is_shutdown = True
        # ThreadPoolExecutor.shutdown は in-flight の完了を待つ
        try:
            self._executor.shutdown(wait=True)
        except Exception:
            _logger.exception("ThreadPoolShortTermMemoryScheduler.shutdown failed")

    def _worker(self, player_id: int, task: L4GenerationTask) -> None:
        start = time.monotonic()
        try:
            task()
        except Exception:
            _logger.exception(
                "ThreadPoolShortTermMemoryScheduler worker task failed for "
                "player_id=%s (latency_ms=%d)",
                player_id,
                int((time.monotonic() - start) * 1000),
            )

    def _on_done(self, future: Future) -> None:
        with self._inflight_lock:
            self._inflight.discard(future)

    def _emit_drop(self, player_id: int, *, reason: str, queue_size: int) -> None:
        if self._trace_recorder_provider is None:
            return
        try:
            recorder = self._trace_recorder_provider()
        except Exception:
            return
        if recorder is None:
            return
        tick: Optional[int] = None
        if self._current_tick_provider is not None:
            try:
                tick = self._current_tick_provider()
            except Exception:
                tick = None
        try:
            recorder.record(
                TraceEventKind.SHORT_TERM_SUMMARY_DROPPED,
                tick=tick,
                player_id=int(player_id),
                reason=reason,
                queue_size=queue_size,
                max_queue_size=self._max_queue_size,
            )
        except Exception:
            _logger.debug(
                "trace recorder.record raised for SHORT_TERM_SUMMARY_DROPPED; skipping",
                exc_info=True,
            )


__all__ = [
    "InlineShortTermMemoryScheduler",
    "IShortTermMemoryScheduler",
    "L4GenerationTask",
    "ThreadPoolShortTermMemoryScheduler",
]
