from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ai_rpg_world.application.being.handlers.record_range_filled_trace_handler import (
    RecordRangeFilledTraceHandler,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import NullTraceRecorder
from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, SeenOrHeard
from ai_rpg_world.being.domain.short_term_memory import Perception, ShortTermMemoryRangeFilledEvent
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.eventing import EventHandler

ADA = BeingId("being_p1")
_AT = datetime(2026, 10, 31, tzinfo=timezone.utc)


def _seen(turn: int) -> Perception:
    observation = Observation(
        body="鐘が鳴った",
        route=SeenOrHeard(),
        time=ObservedTime(display="1日目 朝"),
        subject_is_self=False,
        subject_name=UNKNOWN,
        source=UNKNOWN,
        place=UNKNOWN,
        addressed_to_self=UNKNOWN,
    )
    return Perception(turn=turn, observation=observation)


_EVENT = ShortTermMemoryRangeFilledEvent(
    event_id=1,
    occurred_at=_AT,
    being_id=ADA,
    turn=20,
    until_turn=10,
    experiences=(_seen(1), _seen(2), _seen(3)),
    backstories=(),
)


class _Recorder(NullTraceRecorder):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple[str, int | None, dict[str, Any]]] = []

    def record(self, kind: str, *, tick: int | None = None, player_id: int | None = None, **payload: Any):  # type: ignore[override]
        self.events.append((kind, tick, payload))
        return super().record(kind, tick=tick, player_id=player_id, **payload)


def _handler(recorder: _Recorder | None) -> RecordRangeFilledTraceHandler:
    return RecordRangeFilledTraceHandler(trace_recorder_provider=lambda: recorder, current_tick_provider=lambda: 7)


class TestRecordRangeFilledTraceHandler:
    """RecordRangeFilledTraceHandler が、短期記憶の範囲が埋まったことを trace に残すことを保証する (design_decisions D1824-20)。"""

    def test_range_filled_is_recorded(self) -> None:
        """範囲が埋まったことは、being_short_term_memory_range_filled に、Being・埋まったターン・まとめる範囲の終わり・まとめる出来事の数で残る。埋まったターンは、その範囲で書いたエピソードの書いたターンと同じ。"""
        recorder = _Recorder()

        _handler(recorder).handle(_EVENT)

        assert recorder.events == [
            (
                TraceEventKind.BEING_SHORT_TERM_MEMORY_RANGE_FILLED,
                7,
                {"being_id": "being_p1", "turn": 20, "until_turn": 10, "experience_count": 3},
            )
        ]

    def test_event_is_ignored_without_recorder(self) -> None:
        """trace recorder の無い run では、例外を投げずに何もしない。"""
        _handler(None).handle(_EVENT)

    def test_handler_is_an_event_handler(self) -> None:
        """イベント基盤の同期のハンドラの基底を継ぐ。"""
        assert isinstance(_handler(None), EventHandler)
