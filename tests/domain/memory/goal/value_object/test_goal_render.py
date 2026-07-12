"""render_current_goal (P6): 【現在の目的】描画の分岐を検証する。"""

from __future__ import annotations

from datetime import datetime, timezone

from ai_rpg_world.domain.memory.goal.value_object.goal_entry import (
    GOAL_ORIGIN_SELF,
    GOAL_STATUS_ACTIVE,
    GOAL_UNSET_DISPLAY,
    GoalEntry,
    render_current_goal,
)


def test_none_renders_unset() -> None:
    assert render_current_goal(None) == GOAL_UNSET_DISPLAY == "(まだ定まっていない)"


def test_active_renders_text() -> None:
    entry = GoalEntry(
        goal_id="g1", player_id=1, text="山頂を目指す", status=GOAL_STATUS_ACTIVE,
        locked=False, origin=GOAL_ORIGIN_SELF, created_tick=0,
        created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
    )
    assert render_current_goal(entry) == "山頂を目指す"
