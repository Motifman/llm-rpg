"""Being の短期記憶で起きたことのうち、trace に残すだけのものを残す (#1824、design_decisions D1824-18)。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import ITraceRecorder
from ai_rpg_world.being.domain.short_term_memory import (
    ShortTermMemoryBackstoryAddedEvent,
    ShortTermMemoryOldestTurnsDroppedEvent,
)
from ai_rpg_world.eventing import EventHandler

RecordedShortTermMemoryEvent = ShortTermMemoryOldestTurnsDroppedEvent | ShortTermMemoryBackstoryAddedEvent


class RecordShortTermMemoryTraceHandler(EventHandler[RecordedShortTermMemoryEvent]):
    """trace recorder の無い run では、何もせずに戻る。"""

    def __init__(
        self,
        *,
        trace_recorder_provider: Callable[[], ITraceRecorder | None],
        current_tick_provider: Callable[[], int | None],
    ) -> None:
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider

    def handle(self, event: RecordedShortTermMemoryEvent) -> None:
        recorder = self._trace_recorder_provider()
        if recorder is None:
            return
        kind, payload = _trace_of(event)
        recorder.record(kind, tick=self._current_tick_provider(), being_id=event.being_id.value, **payload)


def _trace_of(event: RecordedShortTermMemoryEvent) -> tuple[str, dict[str, Any]]:
    # trace の種類の名前は保存済みの trace と合わせるため、イベントの名前に合わせて変えない。
    if isinstance(event, ShortTermMemoryOldestTurnsDroppedEvent):
        return TraceEventKind.BEING_SHORT_TERM_MEMORY_FOLD_FORCED, {
            "turn": event.turn,
            "until_turn": event.until_turn,
            "dropped_count": len(event.dropped),
        }
    if isinstance(event, ShortTermMemoryBackstoryAddedEvent):
        backstory = event.backstory
        return TraceEventKind.BEING_BACKSTORY_WRITTEN, {
            "until_turn": backstory.until_turn,
            "written_turn": backstory.written_turn,
            "flow": backstory.flow,
            "mood": backstory.mood,
            "dropped_count": len(event.dropped),
        }
    raise TypeError(f"no trace is defined for {type(event).__name__}")


__all__ = ["RecordShortTermMemoryTraceHandler", "RecordedShortTermMemoryEvent"]
