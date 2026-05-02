"""ObservationExperienceTrace store のテスト。"""

from datetime import datetime, timedelta

import pytest

from ai_rpg_world.application.llm.contracts.dtos import ObservationExperienceTrace
from ai_rpg_world.application.llm.services.in_memory_observation_experience_trace_store import (
    InMemoryObservationExperienceTraceStore,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _trace(
    trace_id: str,
    agent_id: int,
    occurred_at: datetime,
) -> ObservationExperienceTrace:
    return ObservationExperienceTrace(
        trace_id=trace_id,
        agent_id=agent_id,
        occurred_at=occurred_at,
        observation_summary="誰かが部屋に入ってきた。",
        observation_kind="other_agent_action",
        structured={"type": "entity_entered_spot", "actor": "Alice"},
    )


def test_append_and_get_recent_returns_newest_first() -> None:
    store = InMemoryObservationExperienceTraceStore()
    player_id = PlayerId(1)
    older = _trace("old", 1, datetime.now() - timedelta(seconds=10))
    newer = _trace("new", 1, datetime.now())

    store.append(player_id, older)
    store.append(player_id, newer)

    assert [trace.trace_id for trace in store.get_recent(player_id, 10)] == [
        "new",
        "old",
    ]


def test_append_rejects_agent_id_mismatch() -> None:
    store = InMemoryObservationExperienceTraceStore()

    with pytest.raises(ValueError, match="trace.agent_id"):
        store.append(PlayerId(1), _trace("x", 2, datetime.now()))
