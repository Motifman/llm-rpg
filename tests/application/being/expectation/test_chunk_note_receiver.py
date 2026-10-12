"""外れたで確定した予期を、次に閉じる chunk の主観補完に渡す受け取る側の挙動を保証する。"""

from __future__ import annotations

from typing import Any

from tests.trace_helpers import RecordingTraceRecorder

from ai_rpg_world.application.being.expectation.chunk_note import (
    ExpectationChunkNoteReceiver,
)
from ai_rpg_world.application.llm.contracts.chunk_encoding import (
    SettledMissedExpectation,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.expectation.event.expectation_events import (
    ExpectationSettled,
    ProvisionallyMissed,
)
from ai_rpg_world.domain.memory.expectation.value_object.check_verdict import (
    Outcome,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_event_id import (
    ExpectationEventId,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_grounds import (
    ExpectationGrounds,
)
from ai_rpg_world.domain.memory.expectation.value_object.expectation_id import (
    ExpectationId,
)
from ai_rpg_world.domain.memory.expectation.value_object.likelihood import (
    Likelihood,
)

RIO = BeingId("being-rio")
EVENT_ID = ExpectationEventId("exp-1@5")


class _Sink:
    def __init__(self) -> None:
        self.noted: list[tuple[BeingId, SettledMissedExpectation]] = []

    def note_settled_miss(self, being_id: BeingId, missed: SettledMissedExpectation) -> bool:
        if any(m.event_id == missed.event_id for _, m in self.noted):
            return False
        self.noted.append((being_id, missed))
        return True


def _settled(outcome: Outcome) -> ExpectationSettled:
    return ExpectationSettled(
        expectation_id=ExpectationId("exp-1"),
        holder=RIO,
        turn=5,
        content="干潟で貝が採れる",
        outcome=outcome,
        likelihood=Likelihood.EVEN,
        grounds=ExpectationGrounds(),
    )


def _harness() -> tuple[_Sink, RecordingTraceRecorder, ExpectationChunkNoteReceiver]:
    sink = _Sink()
    recorder = RecordingTraceRecorder()
    return sink, recorder, ExpectationChunkNoteReceiver(sink, trace_recorder_provider=lambda: recorder)


class TestChunkNoteReceiver:
    """外れの確定だけを chunk に渡し、二度目は受け取り済みとして残す挙動を保証する。"""

    def test_settled_miss_is_noted_with_content_and_likelihood(self) -> None:
        """外れたで確定した予期は、出来事の ID・予期の文・確からしさを持って chunk 側に渡る。"""
        sink, recorder, receiver = _harness()

        receiver.receive(EVENT_ID, _settled(Outcome.MISS))

        assert sink.noted == [
            (RIO, SettledMissedExpectation(event_id="exp-1@5", content="干潟で貝が採れる", likelihood=Likelihood.EVEN))
        ]
        (trace,) = recorder.payloads(TraceEventKind.EXPECTATION_MATERIAL)
        assert trace["receiver"] == "chunk_note"
        assert trace["result"] == "appended"

    def test_same_event_twice_is_traced_as_already_received(self) -> None:
        """同じ出来事を二度受け取ると、2 回目は chunk 側が拒み、受け取り済みとして trace に残る。"""
        sink, recorder, receiver = _harness()
        receiver.receive(EVENT_ID, _settled(Outcome.MISS))

        receiver.receive(EVENT_ID, _settled(Outcome.MISS))

        assert len(sink.noted) == 1
        results = [t["result"] for t in recorder.payloads(TraceEventKind.EXPECTATION_MATERIAL)]
        assert results == ["appended", "already_received"]

    def test_hit_and_provisional_miss_are_not_noted(self) -> None:
        """当たりの確定と暫定の外れは chunk に渡さず、trace も残さない。何が違ったかを書く対象ではない。"""
        sink, recorder, receiver = _harness()

        receiver.receive(EVENT_ID, _settled(Outcome.HIT))
        receiver.receive(
            ExpectationEventId("exp-1@4"),
            ProvisionallyMissed(expectation_id=ExpectationId("exp-1"), holder=RIO, turn=4, likelihood=Likelihood.EVEN),
        )

        assert sink.noted == []
        assert recorder.payloads(TraceEventKind.EXPECTATION_MATERIAL) == []
