"""trace を記録して、種類ごとに payload を読み返す recorder。"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.trace import ITraceRecorder, TraceEvent


class RecordingTraceRecorder(ITraceRecorder):
    def __init__(self) -> None:
        self.events: list[TraceEvent] = []

    def record(
        self,
        kind: str,
        *,
        tick: int | None = None,
        player_id: int | None = None,
        **payload: Any,
    ) -> TraceEvent:
        event = TraceEvent(
            seq=len(self.events) + 1,
            timestamp="2026-10-03T00:00:00Z",
            kind=kind,
            tick=tick,
            player_id=player_id,
            payload=dict(payload),
        )
        self.events.append(event)
        return event

    def close(self) -> None:
        return None

    def payloads(self, kind: str) -> list[dict[str, Any]]:
        return [event.payload for event in self.events if event.kind == kind]


__all__ = ["RecordingTraceRecorder"]
