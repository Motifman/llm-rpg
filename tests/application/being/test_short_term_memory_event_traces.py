from __future__ import annotations

from datetime import datetime, timezone

from ai_rpg_world.application.being.short_term_memory_event_traces import ShortTermMemoryEventTraces
from ai_rpg_world.being.domain.short_term_memory import ShortTermMemoryOldestTurnsDroppedEvent
from ai_rpg_world.domain.being.value_object.being_id import BeingId

ADA = BeingId("being_p1")
_AT = datetime(2026, 10, 25, tzinfo=timezone.utc)


class TestWithoutRecorder:
    """trace recorder の無い run で、ShortTermMemoryEventTraces が何もせずに戻ることを保証する。"""

    def test_events_are_ignored_without_recorder(self) -> None:
        """recorder が None なら、待たずに古いターンを外したことを、例外を投げずに何もしない。ハンドラの失敗として配送器の知らせ先に積まれないため。"""
        traces = ShortTermMemoryEventTraces(trace_recorder_provider=lambda: None, current_tick_provider=lambda: 3)

        traces.oldest_turns_dropped(
            ShortTermMemoryOldestTurnsDroppedEvent(
                event_id=1, occurred_at=_AT, being_id=ADA, turn=40, until_turn=10, dropped=()
            )
        )
