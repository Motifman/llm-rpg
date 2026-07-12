"""GoalEntry (目的層 P5) の不変条件を検証する。"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from ai_rpg_world.domain.memory.goal.exception.goal_exception import (
    GoalEntryValidationException,
)
from ai_rpg_world.domain.memory.goal.value_object.goal_entry import (
    GOAL_ORIGIN_SCENARIO,
    GOAL_STATUS_ACTIVE,
    MAX_GOAL_TEXT_CHARS,
    GoalEntry,
)


def _entry(**overrides) -> GoalEntry:
    base = dict(
        goal_id="goal-1",
        player_id=1,
        text="山頂で狼煙を上げて救助される",
        status=GOAL_STATUS_ACTIVE,
        locked=True,
        origin=GOAL_ORIGIN_SCENARIO,
        created_tick=0,
        created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    base.update(overrides)
    return GoalEntry(**base)


class TestGoalEntry:
    def test_valid_constructs(self) -> None:
        e = _entry()
        assert e.goal_id == "goal-1"
        assert e.status == "active"
        assert e.locked is True
        assert e.origin == "scenario"
        assert e.supersedes is None

    def test_blank_goal_id_raises(self) -> None:
        with pytest.raises(GoalEntryValidationException):
            _entry(goal_id="  ")

    def test_blank_text_raises(self) -> None:
        with pytest.raises(GoalEntryValidationException):
            _entry(text="   ")

    def test_text_over_max_raises(self) -> None:
        with pytest.raises(GoalEntryValidationException):
            _entry(text="あ" * (MAX_GOAL_TEXT_CHARS + 1))

    def test_invalid_status_raises(self) -> None:
        with pytest.raises(GoalEntryValidationException):
            _entry(status="paused")

    def test_invalid_origin_raises(self) -> None:
        with pytest.raises(GoalEntryValidationException):
            _entry(origin="external")

    def test_non_bool_locked_raises(self) -> None:
        with pytest.raises(GoalEntryValidationException):
            _entry(locked="yes")

    def test_negative_created_tick_raises(self) -> None:
        with pytest.raises(GoalEntryValidationException):
            _entry(created_tick=-1)

    def test_supersedes_stripped(self) -> None:
        e = _entry(supersedes="  goal-0  ")
        assert e.supersedes == "goal-0"
