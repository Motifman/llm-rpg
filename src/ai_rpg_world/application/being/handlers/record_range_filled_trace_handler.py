"""Being の短期記憶の範囲が埋まったことを、trace に残す (#1824、design_decisions D1824-20)。

範囲ごとに、埋まったことと、その範囲で書いたエピソード (being_episode_written) を突き合わせ、0 件だった範囲を見るため。
"""

from __future__ import annotations

from collections.abc import Callable

from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import ITraceRecorder
from ai_rpg_world.being.domain.short_term_memory import ShortTermMemoryRangeFilledEvent
from ai_rpg_world.eventing import EventHandler


class RecordRangeFilledTraceHandler(EventHandler[ShortTermMemoryRangeFilledEvent]):
    """trace recorder の無い run では、何もせずに戻る。"""

    def __init__(
        self,
        *,
        trace_recorder_provider: Callable[[], ITraceRecorder | None],
        current_tick_provider: Callable[[], int | None],
    ) -> None:
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider

    def handle(self, event: ShortTermMemoryRangeFilledEvent) -> None:
        recorder = self._trace_recorder_provider()
        if recorder is None:
            return
        recorder.record(
            TraceEventKind.BEING_SHORT_TERM_MEMORY_RANGE_FILLED,
            tick=self._current_tick_provider(),
            being_id=event.being_id.value,
            turn=event.turn,
            until_turn=event.until_turn,
            experience_count=len(event.experiences),
        )


__all__ = ["RecordRangeFilledTraceHandler"]
