from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from ai_rpg_world.application.being.handlers.record_episode_written_trace_handler import (
    RecordEpisodeWrittenTraceHandler,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.application.trace.recorder import NullTraceRecorder
from ai_rpg_world.being.domain.being_id import BeingId
from ai_rpg_world.being.domain.episode import EpisodeIndex, EpisodeWrittenEvent
from ai_rpg_world.eventing import EventHandler

ADA = BeingId("being_p1")
_AT = datetime(2026, 10, 31, tzinfo=timezone.utc)
_EVENT = EpisodeWrittenEvent(
    event_id=1,
    occurred_at=_AT,
    being_id=ADA,
    episode_id="3f2a7b9c-1d2e-4f00-8a00-000000000001",
    handle="ep_3f2a7b",
    environment_name="廃坑の山村",
    written_turn=20,
    index=EpisodeIndex(summary="鐘の記憶", recall_when="鐘の話が出たとき"),
    body="鐘が鳴った。",
    truncated={"body": 405},
    rewritten=True,
)


class _Recorder(NullTraceRecorder):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[tuple[str, int | None, dict[str, Any]]] = []

    def record(self, kind: str, *, tick: int | None = None, player_id: int | None = None, **payload: Any):  # type: ignore[override]
        self.events.append((kind, tick, payload))
        return super().record(kind, tick=tick, player_id=player_id, **payload)


def _handler(recorder: _Recorder | None) -> RecordEpisodeWrittenTraceHandler:
    return RecordEpisodeWrittenTraceHandler(trace_recorder_provider=lambda: recorder, current_tick_provider=lambda: 7)


class TestRecordEpisodeWrittenTraceHandler:
    """RecordEpisodeWrittenTraceHandler が、書き起こしたエピソードを 1 件ずつ trace に残すことを保証する (design_decisions D1824-19)。"""

    def test_episode_written_is_recorded(self) -> None:
        """書き起こしたエピソードは、being_episode_written に、Being・呼び名・環境・書いたターン・目次・本文の長さ・切り詰めた項目と元の長さ・書き直させたかで残る。"""
        recorder = _Recorder()

        _handler(recorder).handle(_EVENT)

        assert recorder.events == [
            (
                TraceEventKind.BEING_EPISODE_WRITTEN,
                7,
                {
                    "being_id": "being_p1",
                    "handle": "ep_3f2a7b",
                    "environment_name": "廃坑の山村",
                    "written_turn": 20,
                    "summary": "鐘の記憶",
                    "recall_when": "鐘の話が出たとき",
                    "body_length": 6,
                    "truncated": {"body": 405},
                    "rewritten": True,
                },
            )
        ]

    def test_event_is_ignored_without_recorder(self) -> None:
        """trace recorder の無い run では、例外を投げずに何もしない。"""
        _handler(None).handle(_EVENT)

    def test_handler_is_an_event_handler(self) -> None:
        """イベント基盤の同期のハンドラの基底を継ぐ。"""
        assert isinstance(_handler(None), EventHandler)
