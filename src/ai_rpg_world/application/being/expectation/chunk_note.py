"""外れたで確定した予期を、次に閉じる chunk の主観補完に渡す受け取る側。

主観補完 LLM は外れたかどうかを判断せず、渡された外れについて何が違ったかだけを
書く (#1443)。外れの判定は予期の清算だけが持つ。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from ai_rpg_world.application.being.expectation.event_delivery import (
    ExpectationEventReceiver,
)
from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    SettledMissedExpectation,
)
from ai_rpg_world.application.trace import ITraceRecorder, TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.event.expectation_events import (
    ExpectationEvent,
    ExpectationSettled,
)
from ai_rpg_world.domain.memory.expectation.value_object.check_verdict import (
    Outcome,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_event_id import (
    ExpectationEventId,
)


class SettledMissSink(Protocol):
    def note_settled_miss(
        self, being_id: BeingId, missed: SettledMissedExpectation
    ) -> bool:
        """受け取り済みの出来事なら持たずに False を返す。"""
        ...


class ExpectationChunkNoteReceiver(ExpectationEventReceiver):
    """``ExpectationSettled`` の外れだけを ``SettledMissSink`` に渡す。"""

    def __init__(
        self,
        sink: SettledMissSink,
        *,
        trace_recorder_provider: Callable[[], ITraceRecorder | None],
    ) -> None:
        if not callable(getattr(sink, "note_settled_miss", None)):
            raise TypeError("sink must implement note_settled_miss")
        self._sink = sink
        self._trace_recorder_provider = trace_recorder_provider

    def receive(self, event_id: ExpectationEventId, event: ExpectationEvent) -> None:
        if not isinstance(event, ExpectationSettled) or event.outcome is not Outcome.MISS:
            return
        noted = self._sink.note_settled_miss(
            event.holder,
            SettledMissedExpectation(
                event_id=event_id.value,
                content=event.content,
                likelihood=event.likelihood,
            ),
        )
        recorder = self._trace_recorder_provider()
        if recorder is None:
            return
        recorder.record(
            TraceEventKind.EXPECTATION_MATERIAL,
            being_id=event.holder.value,
            event_id=event_id.value,
            expectation_id=event.expectation_id.value,
            receiver="chunk_note",
            outcome=event.outcome.value,
            likelihood=event.likelihood.value,
            result="appended" if noted else "already_received",
        )


__all__ = ["ExpectationChunkNoteReceiver", "SettledMissSink"]
