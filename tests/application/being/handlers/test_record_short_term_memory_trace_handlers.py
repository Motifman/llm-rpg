from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from ai_rpg_world.application.being.handlers.record_backstory_added_trace_handler import (
    RecordBackstoryAddedTraceHandler,
)
from ai_rpg_world.application.being.handlers.record_oldest_turns_dropped_trace_handler import (
    RecordOldestTurnsDroppedTraceHandler,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import NullTraceRecorder
from ai_rpg_world.being.contract import UNKNOWN, Observation, ObservedTime, SeenOrHeard
from ai_rpg_world.being.domain.short_term_memory import (
    Backstory,
    Perception,
    ShortTermMemoryBackstoryAddedEvent,
    ShortTermMemoryEvent,
    ShortTermMemoryOldestTurnsDroppedEvent,
)
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


class _Recorder(NullTraceRecorder):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple[str, int | None, dict[str, Any]]] = []

    def record(self, kind: str, *, tick: int | None = None, player_id: int | None = None, **payload: Any):  # type: ignore[override]
        self.events.append((kind, tick, payload))
        return super().record(kind, tick=tick, player_id=player_id, **payload)


def _providers(recorder: _Recorder | None) -> dict[str, Any]:
    return {"trace_recorder_provider": lambda: recorder, "current_tick_provider": lambda: 7}


def _dropped(*dropped: Perception) -> ShortTermMemoryOldestTurnsDroppedEvent:
    return ShortTermMemoryOldestTurnsDroppedEvent(
        event_id=1, occurred_at=_AT, being_id=ADA, turn=40, until_turn=10, dropped=dropped
    )


class TestRecordOldestTurnsDroppedTraceHandler:
    """RecordOldestTurnsDroppedTraceHandler が、上限で古いターンを外したことを trace に残すことを保証する。"""

    def test_oldest_turns_dropped_is_recorded(self) -> None:
        """上限で古いターンを外したことは、being_short_term_memory_fold_forced に、Being・ターン・外した範囲の終わり・外した出来事の数で残る。"""
        recorder = _Recorder()

        RecordOldestTurnsDroppedTraceHandler(**_providers(recorder)).handle(_dropped(_seen(1), _seen(2)))

        assert recorder.events == [
            (
                TraceEventKind.BEING_SHORT_TERM_MEMORY_FOLD_FORCED,
                7,
                {"being_id": "being_p1", "turn": 40, "until_turn": 10, "dropped_count": 2},
            )
        ]

    def test_event_is_ignored_without_recorder(self) -> None:
        """trace recorder の無い run では、例外を投げずに何もしない。ハンドラの失敗として配送器の知らせ先に積まれないため。"""
        RecordOldestTurnsDroppedTraceHandler(**_providers(None)).handle(_dropped())

    def test_handler_is_an_event_handler(self) -> None:
        """イベント基盤の同期のハンドラの基底を継ぐ (CLAUDE.md のハンドラの決まり)。"""
        assert isinstance(RecordOldestTurnsDroppedTraceHandler(**_providers(None)), EventHandler)


class TestRecordBackstoryAddedTraceHandler:
    """RecordBackstoryAddedTraceHandler が、いきさつが入ったことを trace に残すことを保証する。"""

    def test_backstory_added_is_recorded(self) -> None:
        """いきさつが入ったことは、being_backstory_written に、Being・範囲の終わり・書いたターン・流れ・気分・外した出来事の数で残る。"""
        recorder = _Recorder()
        backstory = Backstory(flow="鐘のあと扉が開いた", mood="落ち着かない", written_turn=20, until_turn=10)

        RecordBackstoryAddedTraceHandler(**_providers(recorder)).handle(
            ShortTermMemoryBackstoryAddedEvent(
                event_id=2, occurred_at=_AT, being_id=ADA, backstory=backstory, dropped=(_seen(1),)
            )
        )

        assert recorder.events == [
            (
                TraceEventKind.BEING_BACKSTORY_WRITTEN,
                7,
                {
                    "being_id": "being_p1",
                    "until_turn": 10,
                    "written_turn": 20,
                    "flow": "鐘のあと扉が開いた",
                    "mood": "落ち着かない",
                    "dropped_count": 1,
                },
            )
        ]

    def test_event_is_ignored_without_recorder(self) -> None:
        """trace recorder の無い run では、例外を投げずに何もしない。"""
        backstory = Backstory(flow="流れ", mood="", written_turn=20, until_turn=10)

        RecordBackstoryAddedTraceHandler(**_providers(None)).handle(
            ShortTermMemoryBackstoryAddedEvent(
                event_id=2, occurred_at=_AT, being_id=ADA, backstory=backstory, dropped=()
            )
        )

    def test_handler_is_an_event_handler(self) -> None:
        """イベント基盤の同期のハンドラの基底を継ぐ。"""
        assert isinstance(RecordBackstoryAddedTraceHandler(**_providers(None)), EventHandler)
