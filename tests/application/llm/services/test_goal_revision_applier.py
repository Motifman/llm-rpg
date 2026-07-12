"""GoalRevisionApplier (P6): goal_update を goal store に反映する挙動を検証する。"""

from __future__ import annotations

from datetime import datetime, timezone

from ai_rpg_world.application.llm.services.goal_revision_applier import (
    GOAL_LOCKED_REJECTION_OBSERVATION,
    GoalRevisionApplier,
)
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
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_BEING = BeingId("being-1")
_PLAYER = PlayerId(1)
_NOW = datetime(2026, 7, 1, tzinfo=timezone.utc)


def _make(store=None, tick=5):
    store = store or InMemoryGoalJournalStore()
    observations: list[tuple] = []
    applier = GoalRevisionApplier(
        store,
        observation_sink=lambda pid, msg: observations.append((pid, msg)),
        current_tick_provider=lambda: tick,
        now_provider=lambda: _NOW,
    )
    return applier, store, observations


def _goal(goal_id, text, *, locked, origin, status=GOAL_STATUS_ACTIVE) -> GoalEntry:
    return GoalEntry(
        goal_id=goal_id, player_id=1, text=text, status=status, locked=locked,
        origin=origin, created_tick=0, created_at=_NOW,
    )


class TestGoalRevisionApplier:
    def test_no_active_goal_adds_new_self_goal(self) -> None:
        applier, store, obs = _make()
        result = applier.apply(_BEING, _PLAYER, "この島の全容を知りたい")
        assert result is not None
        active = store.get_active_by_being(_BEING)
        assert active.text == "この島の全容を知りたい"
        assert active.origin == GOAL_ORIGIN_SELF
        assert active.locked is False
        assert obs == []

    def test_unlocked_active_is_superseded(self) -> None:
        store = InMemoryGoalJournalStore()
        store.add_by_being(_BEING, _goal("g1", "魚を分けてもらう", locked=False, origin=GOAL_ORIGIN_SELF))
        applier, store, obs = _make(store=store)

        result = applier.apply(_BEING, _PLAYER, "自力で食料源を確保する")

        assert result is not None
        entries = {e.goal_id: e for e in store.list_all_by_being(_BEING)}
        assert entries["g1"].status == GOAL_STATUS_SUPERSEDED  # 旧目的は履歴に残る
        active = store.get_active_by_being(_BEING)
        assert active.text == "自力で食料源を確保する"
        assert active.supersedes == "g1"
        assert obs == []

    def test_locked_active_is_rejected_with_observation(self) -> None:
        """locked (シナリオ目的) への書き換えは拒否し、観測で本人に返す

        (silent にしない)。goal store は変わらない。"""
        store = InMemoryGoalJournalStore()
        store.add_by_being(_BEING, _goal("g0", "山頂で狼煙を上げる", locked=True, origin=GOAL_ORIGIN_SCENARIO))
        applier, store, obs = _make(store=store)

        result = applier.apply(_BEING, _PLAYER, "この島で暮らす")

        assert result is None
        # 書き換わっていない。
        assert store.get_active_by_being(_BEING).goal_id == "g0"
        assert len(store.list_all_by_being(_BEING)) == 1
        # 拒否が観測として本人に届く (silent でない)。
        assert obs == [(_PLAYER, GOAL_LOCKED_REJECTION_OBSERVATION)]

    def test_empty_goal_update_is_noop(self) -> None:
        applier, store, obs = _make()
        assert applier.apply(_BEING, _PLAYER, None) is None
        assert applier.apply(_BEING, _PLAYER, "   ") is None
        assert store.list_all_by_being(_BEING) == []
        assert obs == []
