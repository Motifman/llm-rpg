"""Being がエピソードを書き起こして記憶に加えたことを、エピソードごとに trace に残す (#1824、design_decisions D1824-19)。"""

from __future__ import annotations

from collections.abc import Callable

from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import ITraceRecorder
from ai_rpg_world.being.domain.episode import EpisodeWrittenEvent
from ai_rpg_world.eventing import EventHandler


class RecordEpisodeWrittenTraceHandler(EventHandler[EpisodeWrittenEvent]):
    """trace recorder の無い run では、何もせずに戻る。"""

    def __init__(
        self,
        *,
        trace_recorder_provider: Callable[[], ITraceRecorder | None],
        current_tick_provider: Callable[[], int | None],
    ) -> None:
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider

    def handle(self, event: EpisodeWrittenEvent) -> None:
        recorder = self._trace_recorder_provider()
        if recorder is None:
            return
        recorder.record(
            TraceEventKind.BEING_EPISODE_WRITTEN,
            tick=self._current_tick_provider(),
            being_id=event.being_id.value,
            handle=event.handle,
            environment_name=event.environment_name,
            written_turn=event.written_turn,
            summary=event.index.summary,
            recall_when=event.index.recall_when,
            body_length=len(event.body),
            truncated=dict(event.truncated),
        )


__all__ = ["RecordEpisodeWrittenTraceHandler"]
