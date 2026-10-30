"""Being の短期記憶がためたイベントのうち、受け手が trace だけのものを残す (#1824、design_decisions D1824-11)。"""

from __future__ import annotations

from collections.abc import Callable

from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import ITraceRecorder
from ai_rpg_world.being.domain.short_term_memory import FoldForced, StaleBackstoryDiscarded


class ShortTermMemoryEventTraces:
    def __init__(
        self,
        *,
        trace_recorder_provider: Callable[[], ITraceRecorder | None],
        current_tick_provider: Callable[[], int | None],
    ) -> None:
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider

    def fold_forced(self, event: FoldForced) -> None:
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

    def backstory_discarded(self, event: StaleBackstoryDiscarded) -> None:
        recorder = self._trace_recorder_provider()
        if recorder is None:
            return
        recorder.record(
            TraceEventKind.BEING_BACKSTORY_DISCARDED,
            tick=self._current_tick_provider(),
            being_id=event.being_id.value,
            until_turn=event.backstory.until_turn,
            latest_until_turn=event.latest_until_turn,
        )


__all__ = ["ShortTermMemoryEventTraces"]
