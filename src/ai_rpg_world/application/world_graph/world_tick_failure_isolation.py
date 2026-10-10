"""世界の tick の 1 体ぶんの処理の例外を、trace に残して取りやめるか止めるかを決める (design_decisions D1558)。"""

from __future__ import annotations

import logging
import threading
import traceback
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from enum import Enum

from ai_rpg_world.application.common.exceptions import CommandPostCommitException
from ai_rpg_world.application.trace.events import TraceEventKind
from ai_rpg_world.application.trace.recorder import ITraceRecorder
from ai_rpg_world.domain.common.value_object import WorldTick

_logger = logging.getLogger(__name__)

_MAX_MESSAGE_CHARS = 500


class WorldTickFailurePolicy(str, Enum):
    ISOLATE = "isolate"
    FAIL_FAST = "fail_fast"

    @classmethod
    def parse(cls, raw: str) -> WorldTickFailurePolicy:
        normalized = raw.strip().lower()
        for policy in cls:
            if policy.value == normalized:
                return policy
        raise ValueError(
            f"world tick failure policy {raw!r} is not recognized. "
            f"valid: {sorted(p.value for p in cls)}"
        )


class WorldTickFailureIsolator:
    def __init__(
        self,
        *,
        policy: WorldTickFailurePolicy,
        trace_recorder_provider: Callable[[], ITraceRecorder | None],
    ) -> None:
        self._policy = policy
        self._trace_recorder_provider = trace_recorder_provider
        self._counts: dict[str, int] = {}
        # LLM のターンは並列の worker から入ってくる。
        self._lock = threading.Lock()

    @classmethod
    def fail_fast(cls) -> WorldTickFailureIsolator:
        return cls(policy=WorldTickFailurePolicy.FAIL_FAST, trace_recorder_provider=lambda: None)

    @property
    def policy(self) -> WorldTickFailurePolicy:
        return self._policy

    def failure_counts(self) -> dict[str, int]:
        with self._lock:
            return dict(self._counts)

    @contextmanager
    def unit(
        self,
        *,
        stage: str,
        tick: WorldTick,
        target_kind: str,
        target_id: int | str | None = None,
        player_id: int | None = None,
    ) -> Iterator[None]:
        try:
            yield
        except Exception as exc:
            recorder = self._trace_recorder_provider()
            if recorder is None:
                # trace に残せない取りやめは静かな失敗になるので、止める。
                raise
            try:
                recorder.record(
                    TraceEventKind.WORLD_TICK_UNIT_FAILED,
                    tick=tick.value,
                    player_id=player_id,
                    stage=stage,
                    target_kind=target_kind,
                    target_id=target_id,
                    error_type=type(exc).__name__,
                    error_message=_truncate(str(exc)),
                    error_origin=_innermost_frame(exc),
                    committed=isinstance(exc, CommandPostCommitException),
                    policy=self._policy.value,
                )
            except Exception:
                _logger.exception(
                    "failed to record world_tick_unit_failed (stage=%s target=%s:%s)",
                    stage, target_kind, target_id,
                )
                raise exc
            with self._lock:
                self._counts[stage] = self._counts.get(stage, 0) + 1
            if self._policy is WorldTickFailurePolicy.FAIL_FAST:
                raise
            _logger.error(
                "world tick unit skipped (stage=%s target=%s:%s tick=%s)",
                stage, target_kind, target_id, tick.value,
                exc_info=True,
            )


def _truncate(message: str) -> str:
    if len(message) <= _MAX_MESSAGE_CHARS:
        return message
    return message[:_MAX_MESSAGE_CHARS] + "…"


def _innermost_frame(exc: BaseException) -> str | None:
    frames = traceback.extract_tb(exc.__traceback__)
    if not frames:
        return None
    frame = frames[-1]
    return f"{frame.filename}:{frame.lineno} in {frame.name}"


__all__ = ["WorldTickFailureIsolator", "WorldTickFailurePolicy"]
