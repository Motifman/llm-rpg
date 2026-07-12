"""GoalRevisionApplier (P6/P8): goal_update (立て直し) と goal_outcome (清算) を
goal store に反映する挙動を検証する。"""

from __future__ import annotations

from datetime import datetime, timezone

from ai_rpg_world.application.llm.services.goal_revision_applier import (
    GOAL_LOCKED_REJECTION_OBSERVATION,
    GoalRevisionApplier,
)
from ai_rpg_world.application.llm.services.in_memory_goal_journal_store import (
    InMemoryGoalJournalStore,
)
from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.goal.value_object.goal_entry import (
    GOAL_ORIGIN_SCENARIO,
    GOAL_ORIGIN_SELF,
    GOAL_STATUS_ABANDONED,
    GOAL_STATUS_ACHIEVED,
    GOAL_STATUS_ACTIVE,
    GOAL_STATUS_SUPERSEDED,
    GoalEntry,
)
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

_BEING = BeingId("being-1")
_PLAYER = PlayerId(1)
_NOW = datetime(2026, 7, 1, tzinfo=timezone.utc)


class _FakeSettlementTranscriber:
    """record_goal_resolution の呼び出しを記録する fake (buffer には積まない)。"""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def record_goal_resolution(self, being_id, goal, *, outcome, occurred_at):
        self.calls.append((being_id, goal.goal_id, outcome, occurred_at))

        class _Ev:
            evidence_id = f"ev-{goal.goal_id}-{outcome}"

        return _Ev()


class _FakeTrace:
    def __init__(self) -> None:
        self.records: list[tuple] = []

    def record(self, kind, **payload):
        self.records.append((kind, payload))


def _make(store=None, tick=5, *, transcriber=None, trace=None):
    store = store or InMemoryGoalJournalStore()
    observations: list[tuple] = []
    applier = GoalRevisionApplier(
        store,
        observation_sink=lambda pid, msg: observations.append((pid, msg)),
        current_tick_provider=lambda: tick,
        now_provider=lambda: _NOW,
        settlement_transcriber_provider=(lambda: transcriber),
        trace_recorder_provider=(lambda: trace),
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
        result = applier.apply(
            _BEING, _PLAYER, goal_update_text="この島の全容を知りたい", goal_outcome=None
        )
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

        result = applier.apply(
            _BEING, _PLAYER, goal_update_text="自力で食料源を確保する", goal_outcome=None
        )

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

        result = applier.apply(
            _BEING, _PLAYER, goal_update_text="この島で暮らす", goal_outcome=None
        )

        assert result is None
        # 書き換わっていない。
        assert store.get_active_by_being(_BEING).goal_id == "g0"
        assert len(store.list_all_by_being(_BEING)) == 1
        # 拒否が観測として本人に届く (silent でない)。
        assert obs == [(_PLAYER, GOAL_LOCKED_REJECTION_OBSERVATION)]

    def test_empty_goal_update_is_noop(self) -> None:
        applier, store, obs = _make()
        assert (
            applier.apply(_BEING, _PLAYER, goal_update_text=None, goal_outcome=None)
            is None
        )
        assert (
            applier.apply(_BEING, _PLAYER, goal_update_text="   ", goal_outcome=None)
            is None
        )
        assert store.list_all_by_being(_BEING) == []
        assert obs == []


class TestGoalOutcomeSettlement:
    """P8: goal_outcome (achieved / abandoned) の清算と転記・trace・組み合わせ。"""

    def test_outcome_with_update_settles_old_and_starts_new(self) -> None:
        """goal_outcome=achieved + goal_update → 旧目的を ACHIEVED で閉じ次へ。"""
        store = InMemoryGoalJournalStore()
        store.add_by_being(
            _BEING, _goal("g1", "古い地図を手に入れる", locked=False, origin=GOAL_ORIGIN_SELF)
        )
        transcriber = _FakeSettlementTranscriber()
        trace = _FakeTrace()
        applier, store, obs = _make(store=store, transcriber=transcriber, trace=trace)

        result = applier.apply(
            _BEING, _PLAYER,
            goal_update_text="地図を頼りに山頂を目指す", goal_outcome="achieved",
        )

        entries = {e.goal_id: e for e in store.list_all_by_being(_BEING)}
        assert entries["g1"].status == GOAL_STATUS_ACHIEVED  # SUPERSEDED ではない
        assert result is not None and result.text == "地図を頼りに山頂を目指す"
        assert result.supersedes == "g1"
        # 転記が achieved で呼ばれ、GOAL_RESOLUTION trace が残る。
        assert transcriber.calls == [(_BEING, "g1", "achieved", _NOW)]
        kinds = [k for k, _ in trace.records]
        assert TraceEventKind.GOAL_RESOLUTION in kinds

    def test_outcome_only_closes_to_no_goal(self) -> None:
        """goal_outcome=abandoned のみ → 旧目的を ABANDONED で閉じ無目的に戻る。"""
        store = InMemoryGoalJournalStore()
        store.add_by_being(
            _BEING, _goal("g1", "山頂で狼煙を上げる", locked=False, origin=GOAL_ORIGIN_SELF)
        )
        transcriber = _FakeSettlementTranscriber()
        applier, store, obs = _make(store=store, transcriber=transcriber)

        result = applier.apply(
            _BEING, _PLAYER, goal_update_text=None, goal_outcome="abandoned"
        )

        assert result is None  # 無目的に戻る
        assert store.get_active_by_being(_BEING) is None
        entries = {e.goal_id: e for e in store.list_all_by_being(_BEING)}
        assert entries["g1"].status == GOAL_STATUS_ABANDONED
        assert transcriber.calls == [(_BEING, "g1", "abandoned", _NOW)]

    def test_update_only_supersedes_without_transcription(self) -> None:
        """goal_update のみ (言い直し) → SUPERSEDED、清算転記は起きない。"""
        store = InMemoryGoalJournalStore()
        store.add_by_being(
            _BEING, _goal("g1", "魚を分けてもらう", locked=False, origin=GOAL_ORIGIN_SELF)
        )
        transcriber = _FakeSettlementTranscriber()
        trace = _FakeTrace()
        applier, store, obs = _make(store=store, transcriber=transcriber, trace=trace)

        applier.apply(
            _BEING, _PLAYER, goal_update_text="自力で食料を確保する", goal_outcome=None
        )

        entries = {e.goal_id: e for e in store.list_all_by_being(_BEING)}
        assert entries["g1"].status == GOAL_STATUS_SUPERSEDED
        assert transcriber.calls == []  # 言い直しは清算ではない
        assert [k for k, _ in trace.records] == []

    def test_outcome_on_locked_goal_rejected_with_observation(self) -> None:
        """locked (シナリオ目的) への goal_outcome は拒否 + 観測。清算しない。"""
        store = InMemoryGoalJournalStore()
        store.add_by_being(
            _BEING, _goal("g0", "禁書を封印する", locked=True, origin=GOAL_ORIGIN_SCENARIO)
        )
        transcriber = _FakeSettlementTranscriber()
        applier, store, obs = _make(store=store, transcriber=transcriber)

        result = applier.apply(
            _BEING, _PLAYER, goal_update_text=None, goal_outcome="achieved"
        )

        assert result is None
        assert store.get_active_by_being(_BEING).status == GOAL_STATUS_ACTIVE
        assert transcriber.calls == []  # 清算していない
        assert obs == [(_PLAYER, GOAL_LOCKED_REJECTION_OBSERVATION)]

    def test_outcome_without_active_goal_is_noop(self) -> None:
        """active 目的が無いときの goal_outcome は安全な no-op (閉じる対象が無い)。"""
        transcriber = _FakeSettlementTranscriber()
        applier, store, obs = _make(transcriber=transcriber)
        result = applier.apply(
            _BEING, _PLAYER, goal_update_text=None, goal_outcome="achieved"
        )
        assert result is None
        assert transcriber.calls == []
        assert store.list_all_by_being(_BEING) == []

    def test_invalid_new_goal_text_aborts_before_settling(self) -> None:
        """新目的の text が不正なら、清算前に例外で止まり部分コミットにならない。

        新目的の GoalEntry 構築 (検証) を store 変更より先に置くことで、
        「旧目的を閉じて達成 evidence まで残したのに次の目的が立たない」
        部分コミット (silent failure) を防ぐ。旧目的は active のまま・転記も無し。
        """
        store = InMemoryGoalJournalStore()
        store.add_by_being(
            _BEING, _goal("g1", "古い地図を手に入れる", locked=False, origin=GOAL_ORIGIN_SELF)
        )
        transcriber = _FakeSettlementTranscriber()
        applier, store, obs = _make(store=store, transcriber=transcriber)

        # GoalEntry の text 上限を超える長文で構築を失敗させる。
        too_long = "あ" * 500
        try:
            applier.apply(
                _BEING, _PLAYER, goal_update_text=too_long, goal_outcome="achieved"
            )
            raised = False
        except Exception:
            raised = True

        assert raised  # 例外で止まる (world_runtime 側で握られる)
        # 旧目的は閉じられていない (active のまま)、転記も起きていない。
        assert store.get_active_by_being(_BEING).goal_id == "g1"
        assert store.get_active_by_being(_BEING).status == GOAL_STATUS_ACTIVE
        assert transcriber.calls == []
