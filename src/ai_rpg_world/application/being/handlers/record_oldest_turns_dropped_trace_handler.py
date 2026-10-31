"""Being の短期記憶が上限で古いターンを外したことを、trace に残す (#1824、design_decisions D1824-18)。"""

from __future__ import annotations

from collections.abc import Callable

from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import ITraceRecorder
from ai_rpg_world.being.domain.short_term_memory import ShortTermMemoryOldestTurnsDroppedEvent
from ai_rpg_world.eventing import EventHandler


class RecordOldestTurnsDroppedTraceHandler(EventHandler[ShortTermMemoryOldestTurnsDroppedEvent]):
    """trace recorder の無い run では、何もせずに戻る。"""

    def __init__(
        self,
        *,
        trace_recorder_provider: Callable[[], ITraceRecorder | None],
        current_tick_provider: Callable[[], int | None],
    ) -> None:
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider

    def handle(self, event: ShortTermMemoryOldestTurnsDroppedEvent) -> None:
        recorder = self._trace_recorder_provider()
        if recorder is None:
            return
        recorder.record(
            TraceEventKind.BEING_SHORT_TERM_MEMORY_FOLD_FORCED,
            tick=self._current_tick_provider(),
            being_id=event.being_id.value,
            turn=event.turn,
            until_turn=event.until_turn,
            dropped_count=len(event.dropped),
        )


__all__ = ["RecordOldestTurnsDroppedTraceHandler"]
