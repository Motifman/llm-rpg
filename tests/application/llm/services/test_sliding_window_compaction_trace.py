"""要約なしの短期記憶でも、圧縮の発火量を trace から読めることを保証する。"""

from datetime import datetime, timezone
from typing import Any

from ai_rpg_world.application.llm.services.sliding_window_memory import (
    DefaultSlidingWindowMemory,
)
from ai_rpg_world.application.observation.contracts.dtos import (
    ObservationEntry,
    ObservationOutput,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class _Recorder:
    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, Any]]] = []

    def record(self, kind: str, **payload: Any) -> None:
        self.records.append((kind, payload))


def test_sliding_window_compaction_records_the_same_observability_payload() -> None:
    """圧縮方式を切り替えても、発火 tick・ターン数・前後件数の trace は欠けない。"""
    recorder = _Recorder()
    player_id = PlayerId(3)
    memory = DefaultSlidingWindowMemory(
        turn_cap=2,
        compact_turn_count=1,
        trace_recorder_provider=lambda: recorder,
        current_tick_provider=lambda: 9,
    )
    memory.append(
        player_id,
        ObservationEntry(
            occurred_at=datetime(2026, 8, 13, tzinfo=timezone.utc),
            output=ObservationOutput(prose="出来事", structured={}),
        ),
    )

    memory.complete_turn(player_id)
    memory.complete_turn(player_id)

    assert recorder.records == [
        (
            TraceEventKind.SHORT_TERM_MEMORY_COMPACTED,
            {
                "tick": 9,
                "player_id": 3,
                "completed_turn_count_before": 2,
                "completed_turn_count_after": 1,
                "entry_count_before": 1,
                "entry_count_after": 0,
                "compacted_turn_count": 1,
            },
        )
    ]
