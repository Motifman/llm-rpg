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
# fail_fast で内側の単位が記録して投げ直した例外を、外側の段の単位で二重に数えない。
_RECORDED_ATTR = "_world_tick_failure_recorded"


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
        target_id: object = None,
        player_id: int | None = None,
        command_scoped: bool = True,
    ) -> Iterator[None]:
        try:
            yield
        except Exception as exc:
            if getattr(exc, _RECORDED_ATTR, False):
                raise
            recorder = self._trace_recorder_provider()
            if recorder is None:
                # trace に残せない取りやめは静かな失敗になるので、止める。
                raise
            try:
                event = recorder.record(
                    TraceEventKind.WORLD_TICK_UNIT_FAILED,
                    tick=tick.value,
                    player_id=player_id,
                    stage=stage,
                    target_kind=target_kind,
                    target_id=(
                        target_id
                        if target_id is None or isinstance(target_id, (int, str))
                        else str(target_id)
                    ),
                    error_type=type(exc).__name__,
                    error_message=_truncate(str(exc)),
                    error_origin=_innermost_frame(exc),
                    # CommandScope 1 回でない単位では、取りやめる前に何が確定したか分からない。
                    committed=(
                        isinstance(exc, CommandPostCommitException)
                        if command_scoped
                        else None
                    ),
                    policy=self._policy.value,
                )
                if event.seq < 0:
                    # 閉じた recorder は例外を出さずに捨てて seq=-1 を返す。
                    raise RuntimeError("trace recorder dropped world_tick_unit_failed")
            except Exception:
                _logger.exception(
                    "failed to record world_tick_unit_failed (stage=%s target=%s:%s)",
                    stage, target_kind, target_id,
                )
                raise exc
            with self._lock:
                self._counts[stage] = self._counts.get(stage, 0) + 1
            # commit 後の後始末に失敗した transaction 資源は、次の 1 体の scope が
            # 再利用してしまう。1 体の失敗ではないので isolate でも止める。
            if self._policy is WorldTickFailurePolicy.FAIL_FAST or isinstance(
                exc, CommandPostCommitException
            ):
                setattr(exc, _RECORDED_ATTR, True)
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
