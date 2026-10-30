"""試験で trace に残った出来事を読み返すための記録係。"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.trace.events import TraceEvent
from ai_rpg_world.application.trace.recorder import NullTraceRecorder


class CollectingTraceRecorder(NullTraceRecorder):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[TraceEvent] = []

    def record(self, kind: str, **kwargs: Any) -> TraceEvent:
        event = super().record(kind, **kwargs)
        self.events.append(event)
        return event

    def of_kind(self, kind: str) -> list[TraceEvent]:
        return [event for event in self.events if event.kind == kind]
