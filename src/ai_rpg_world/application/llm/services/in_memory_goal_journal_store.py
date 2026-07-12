"""GoalJournalRepository の in-memory 実装 (P5)。

belief journal の in-memory store と同型。Being ごとに GoalEntry の list を
追加順で保持する。実験 runtime は in-memory (snapshot 経由で永続) を使う。
"""

from __future__ import annotations

from collections import defaultdict
from typing import Optional

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.goal.repository.goal_journal_repository import (
    GoalJournalRepository,
)
from ai_rpg_world.domain.memory.goal.value_object.goal_entry import (
    GOAL_STATUS_ACHIEVED,
    GOAL_STATUS_ABANDONED,
    GOAL_STATUS_ACTIVE,
    GOAL_STATUS_SUPERSEDED,
    GoalEntry,
)
from dataclasses import replace

_SETTLE_STATUSES = frozenset({GOAL_STATUS_ACHIEVED, GOAL_STATUS_ABANDONED})


class InMemoryGoalJournalStore(GoalJournalRepository):
    """Being ごとに ``GoalEntry`` の list を保持する。"""

    def __init__(self) -> None:
        self._entries: dict[BeingId, list[GoalEntry]] = defaultdict(list)

    def add_by_being(self, being_id: BeingId, entry: GoalEntry) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(entry, GoalEntry):
            raise TypeError("entry must be GoalEntry")
        self._entries[being_id].append(entry)

    def list_all_by_being(self, being_id: BeingId) -> list[GoalEntry]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        return list(self._entries.get(being_id, ()))

    def get_active_by_being(self, being_id: BeingId) -> Optional[GoalEntry]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        active = [
            e for e in self._entries.get(being_id, ()) if e.status == GOAL_STATUS_ACTIVE
        ]
        return active[-1] if active else None

    def supersede_by_being(
        self,
        being_id: BeingId,
        *,
        old_goal_id: str,
        new_entry: GoalEntry,
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(new_entry, GoalEntry):
            raise TypeError("new_entry must be GoalEntry")
        bucket = self._entries[being_id]
        for i, e in enumerate(bucket):
            if e.goal_id == old_goal_id and e.status == GOAL_STATUS_ACTIVE:
                bucket[i] = replace(e, status=GOAL_STATUS_SUPERSEDED)
                break
        bucket.append(new_entry)

    def settle_by_being(
        self, being_id: BeingId, *, goal_id: str, outcome_status: str
    ) -> Optional[GoalEntry]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if outcome_status not in _SETTLE_STATUSES:
            raise ValueError(
                "outcome_status must be one of "
                f"{sorted(_SETTLE_STATUSES)}, got {outcome_status!r}"
            )
        bucket = self._entries[being_id]
        for i, e in enumerate(bucket):
            if e.goal_id == goal_id and e.status == GOAL_STATUS_ACTIVE:
                settled = replace(e, status=outcome_status)
                bucket[i] = settled
                return settled
        return None

    def replace_all_by_being(
        self, being_id: BeingId, entries: list[GoalEntry]
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(entries, list):
            raise TypeError("entries must be list")
        for e in entries:
            if not isinstance(e, GoalEntry):
                raise TypeError("entries elements must be GoalEntry")
        self._entries[being_id] = list(entries)


__all__ = ["InMemoryGoalJournalStore"]
