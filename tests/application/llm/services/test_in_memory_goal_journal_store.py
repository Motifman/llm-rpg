"""InMemoryGoalJournalStore (目的層 P5) の journal 挙動を検証する。"""

from __future__ import annotations

from datetime import datetime, timezone

from ai_rpg_world.application.llm.services.in_memory_goal_journal_store import (
    InMemoryGoalJournalStore,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.goal.value_object.goal_entry import (
    GOAL_ORIGIN_SCENARIO,
    GOAL_ORIGIN_SELF,
    GOAL_STATUS_ACTIVE,
    GOAL_STATUS_SUPERSEDED,
    GoalEntry,
)

_BEING = BeingId("being-1")


def _goal(goal_id, text, *, status=GOAL_STATUS_ACTIVE, origin=GOAL_ORIGIN_SCENARIO,
          locked=False, supersedes=None) -> GoalEntry:
    return GoalEntry(
        goal_id=goal_id,
        player_id=1,
        text=text,
        status=status,
        locked=locked,
        origin=origin,
        created_tick=0,
        created_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        supersedes=supersedes,
    )


class TestInMemoryGoalJournalStore:
    def test_add_and_get_active(self) -> None:
        store = InMemoryGoalJournalStore()
        store.add_by_being(_BEING, _goal("g1", "生き延びる"))
        active = store.get_active_by_being(_BEING)
        assert active is not None
        assert active.goal_id == "g1"

    def test_get_active_none_when_empty(self) -> None:
        assert InMemoryGoalJournalStore().get_active_by_being(_BEING) is None

    def test_supersede_marks_old_superseded_and_adds_new_active(self) -> None:
        store = InMemoryGoalJournalStore()
        store.add_by_being(_BEING, _goal("g1", "生き延びる"))
        store.supersede_by_being(
            _BEING,
            old_goal_id="g1",
            new_entry=_goal("g2", "島を探索する", origin=GOAL_ORIGIN_SELF, supersedes="g1"),
        )
        # 旧目的は superseded、履歴として残る。
        all_entries = {e.goal_id: e for e in store.list_all_by_being(_BEING)}
        assert all_entries["g1"].status == GOAL_STATUS_SUPERSEDED
        # active は新目的だけ。
        active = store.get_active_by_being(_BEING)
        assert active.goal_id == "g2"
        assert active.supersedes == "g1"

    def test_replace_all_round_trips(self) -> None:
        store = InMemoryGoalJournalStore()
        entries = [_goal("g1", "a", status=GOAL_STATUS_SUPERSEDED), _goal("g2", "b")]
        store.replace_all_by_being(_BEING, entries)
        assert [e.goal_id for e in store.list_all_by_being(_BEING)] == ["g1", "g2"]
        assert store.get_active_by_being(_BEING).goal_id == "g2"
