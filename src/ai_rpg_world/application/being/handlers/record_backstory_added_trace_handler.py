"""Being の短期記憶にいきさつが入ったことを、trace に残す (#1824、design_decisions D1824-18)。"""

from __future__ import annotations

from collections.abc import Callable

from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import ITraceRecorder
from ai_rpg_world.being.domain.short_term_memory import ShortTermMemoryBackstoryAddedEvent
from ai_rpg_world.eventing import EventHandler


class RecordBackstoryAddedTraceHandler(EventHandler[ShortTermMemoryBackstoryAddedEvent]):
    """trace の種類は、保存済みの trace と合わせて being_backstory_written のまま。trace recorder の無い run では、何もせずに戻る。"""

    def __init__(
        self,
        *,
        trace_recorder_provider: Callable[[], ITraceRecorder | None],
        current_tick_provider: Callable[[], int | None],
    ) -> None:
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider

    def handle(self, event: ShortTermMemoryBackstoryAddedEvent) -> None:
        recorder = self._trace_recorder_provider()
        if recorder is None:
            return
        backstory = event.backstory
        recorder.record(
            TraceEventKind.BEING_BACKSTORY_WRITTEN,
            tick=self._current_tick_provider(),
            being_id=event.being_id.value,
            until_turn=backstory.until_turn,
            written_turn=backstory.written_turn,
            flow=backstory.flow,
            mood=backstory.mood,
            dropped_count=len(event.dropped),
            truncated=dict(event.truncated),
        )


__all__ = ["RecordBackstoryAddedTraceHandler"]
