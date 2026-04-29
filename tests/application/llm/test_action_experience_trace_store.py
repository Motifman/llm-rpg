"""ActionExperienceTrace store のテスト。"""

from datetime import datetime, timedelta

import pytest

from ai_rpg_world.application.llm.contracts.dtos import ActionExperienceTrace
from ai_rpg_world.application.llm.services.in_memory_action_experience_trace_store import (
    InMemoryActionExperienceTraceStore,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


def _trace(trace_id: str, agent_id: int, occurred_at: datetime) -> ActionExperienceTrace:
    return ActionExperienceTrace(
        trace_id=trace_id,
        agent_id=agent_id,
        occurred_at=occurred_at,
        tool_name="move_to_destination",
        tool_args={"target_spot_id": 1},
        inner_thought="向こうを確かめたい。",
        intention="隣の部屋へ移動する。",
        expected_result="隣の部屋の様子が分かる。",
        attention="扉の先",
        emotion_hint="curiosity",
        tool_result="移動しました。",
        result_success=True,
    )


def test_append_and_get_recent_returns_newest_first() -> None:
    store = InMemoryActionExperienceTraceStore()
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
    store = InMemoryActionExperienceTraceStore()

    with pytest.raises(ValueError, match="trace.agent_id"):
        store.append(PlayerId(1), _trace("x", 2, datetime.now()))
