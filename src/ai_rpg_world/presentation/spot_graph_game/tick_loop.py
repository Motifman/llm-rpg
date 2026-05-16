"""Background asyncio task that drives wall-clock-paced game ticks.

This module turns the world into a self-running simulation: each running
session has its ``runtime.advance_tick()`` invoked on a fixed interval,
independent of incoming HTTP requests. This is the first step toward the
target architecture where game time progresses on its own and multiple
LLM agents can coexist within the same world.

Why a presentation-layer loop:
    The tick post-hook (``ILlmTurnTrigger.run_scheduled_turns``) is already
    integrated into ``SpotGraphSimulationApplicationService.tick()``. What
    is missing is a *driver* that calls ``tick()`` periodically; that is
    inherently a process-level concern (an asyncio task tied to the
    FastAPI lifespan) rather than a domain or application concern.

Concurrency note:
    The loop runs in the same asyncio event loop as FastAPI request
    handlers. ``advance_tick()`` is synchronous and currently fast (in-
    memory repositories, no I/O). If it ever becomes slow we should
    offload it via ``run_in_executor``; for now keeping things synchronous
    keeps reasoning simple and avoids races on the in-memory state.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from ai_rpg_world.presentation.spot_graph_game.runtime_manager import (
        GameRuntimeManager,
    )

logger = logging.getLogger(__name__)


_MIN_INTERVAL_SECONDS = 0.01
_STOP_GRACE_SECONDS = 2.0
# 連続して同一セッションが N 回失敗したら ERROR で警告する閾値。
# 通常の transient エラーは黙って log.exception に乗せるが、長期間
# 同じセッションが詰まり続けるとオペレータに気付かせる。
_CONSECUTIVE_FAILURE_ALERT_THRESHOLD = 5


def _validate_interval(seconds: float) -> None:
    if seconds < _MIN_INTERVAL_SECONDS:
        raise ValueError(
            f"interval_seconds must be >= {_MIN_INTERVAL_SECONDS}"
        )


@dataclass
class SimulationTickLoop:
    """Drives ``advance_tick()`` on every running session on a fixed cadence."""

    manager: "GameRuntimeManager"
    interval_seconds: float = 1.0
    _task: Optional[asyncio.Task[None]] = field(default=None, init=False, repr=False)
    _stop_event: Optional[asyncio.Event] = field(default=None, init=False, repr=False)
    _consecutive_failures: dict[str, int] = field(
        default_factory=dict, init=False, repr=False
    )

    def __post_init__(self) -> None:
        _validate_interval(self.interval_seconds)

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        """Spawn the loop as an asyncio task. Idempotent."""
        if self.is_running:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(
            self._run(), name="spot_graph_tick_loop"
        )

    async def stop(self) -> None:
        """Signal stop and await graceful shutdown of the loop task."""
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
            logger.warning(
                "Tick loop did not stop within grace period; cancelling"
            )
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
        finally:
            self._task = None
            self._stop_event = None

    def set_interval(self, seconds: float) -> None:
        """Change cadence. Takes effect on the *next* sleep iteration.

        A sleep already in progress finishes at the old interval; this is
        intentional (calling ``set_interval`` is cooperative, not preemptive)
        and keeps the loop free of cancellation gymnastics.
        """
        _validate_interval(seconds)
        self.interval_seconds = seconds

    async def _run(self) -> None:
        stop_event = self._stop_event
        if stop_event is None:
            raise RuntimeError(
                "_run() called without a stop event; use start() instead"
            )
        logger.info(
            "Spot graph tick loop started: interval=%.3fs",
            self.interval_seconds,
        )
        try:
            while not stop_event.is_set():
                # NOTE: advance_tick runs before sleep — if it ever becomes
                # slow (>10ms), offload via run_in_executor so the cadence
                # stays close to interval_seconds. Currently all runtimes
                # operate on in-memory state so the cost is negligible.
                self._tick_all_running_sessions()
                try:
                    await asyncio.wait_for(
                        stop_event.wait(),
                        timeout=self.interval_seconds,
                    )
                except asyncio.TimeoutError:
                    continue
        finally:
            logger.info("Spot graph tick loop stopped")

    def _tick_all_running_sessions(self) -> None:
        # Iterate via a snapshot so concurrent session creation/removal
        # during a tick does not raise RuntimeError on dict mutation.
        active_session_ids: set[str] = set()
        for session_id, runtime in list(self.manager.iter_running_runtimes()):
            active_session_ids.add(session_id)
            try:
                tick_value = runtime.advance_tick()
                logger.debug(
                    "session=%s tick advanced to %s",
                    session_id,
                    tick_value,
                )
                # 成功したら連続失敗カウントをリセット
                if session_id in self._consecutive_failures:
                    del self._consecutive_failures[session_id]
            except Exception:
                # 1 セッションの失敗は loop 自体や他セッションを止めない。
                # ただし連続失敗が閾値を超えたら ERROR レベルでオペレータに
                # 通知する (silent な log.exception 連発で詰まりを見落とすのを
                # 防ぐ)。
                count = self._consecutive_failures.get(session_id, 0) + 1
                self._consecutive_failures[session_id] = count
                if count == _CONSECUTIVE_FAILURE_ALERT_THRESHOLD:
                    logger.error(
                        "session=%s has failed %d ticks in a row; "
                        "manual intervention may be required",
                        session_id,
                        count,
                    )
                logger.exception(
                    "advance_tick failed for session %s (consecutive=%d)",
                    session_id,
                    count,
                )
        # 既に running でなくなったセッションのカウンタを掃除
        for stale_id in list(self._consecutive_failures.keys()):
            if stale_id not in active_session_ids:
                del self._consecutive_failures[stale_id]
