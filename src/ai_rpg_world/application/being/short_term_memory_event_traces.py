"""Being の短期記憶がためたイベントのうち、trace に残すだけのものを残す (#1824、design_decisions D1824-11)。"""

from __future__ import annotations

from collections.abc import Callable

from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import ITraceRecorder
from ai_rpg_world.being.domain.short_term_memory import ShortTermMemoryOldestTurnsDroppedEvent


class ShortTermMemoryEventTraces:
    def __init__(
        self,
        *,
        trace_recorder_provider: Callable[[], ITraceRecorder | None],
        current_tick_provider: Callable[[], int | None],
    ) -> None:
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider

    def oldest_turns_dropped(self, event: ShortTermMemoryOldestTurnsDroppedEvent) -> None:
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


__all__ = ["ShortTermMemoryEventTraces"]
