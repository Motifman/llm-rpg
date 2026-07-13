"""GoalRevisionApplier (P6/P8): goal_update (立て直し) と goal_outcome (清算) を
goal store に反映する挙動を検証する。"""

from __future__ import annotations

from datetime import datetime, timezone

from ai_rpg_world.application.llm.services.goal_revision_applier import (
    GOAL_LOCKED_REJECTION_OBSERVATION,
    GOAL_UPDATE_TEXT_TOO_LONG_OBSERVATION,
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
    SELF_AUTHORED_GOAL_TEXT_MAX_CHARS,
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

    def test_locked_active_is_rejected_with_trace(self) -> None:
        """locked への書き換え拒否が GOAL_REVISION_REJECTED trace に残る

        (見直しを何回試みて拒否されたかを run 分析で数えられるようにする)。
        observation (本人向け) の挙動は変えない。"""
        store = InMemoryGoalJournalStore()
        store.add_by_being(
            _BEING, _goal("g0", "山頂で狼煙を上げる", locked=True, origin=GOAL_ORIGIN_SCENARIO)
        )
        trace = _FakeTrace()
        applier, store, obs = _make(store=store, tick=42, trace=trace)

        result = applier.apply(
            _BEING, _PLAYER, goal_update_text="この島で暮らす", goal_outcome=None
        )

        assert result is None
        assert obs == [(_PLAYER, GOAL_LOCKED_REJECTION_OBSERVATION)]
        rejected = [
            (kind, payload)
            for kind, payload in trace.records
            if kind == TraceEventKind.GOAL_REVISION_REJECTED
        ]
        assert len(rejected) == 1
        _, payload = rejected[0]
        assert payload["being_id"] == str(_BEING.value)
        assert payload["tick"] == 42
        assert payload["reason"] == "locked"
        assert payload["goal_id"] == "g0"
        assert payload["attempted_goal_text"] == "この島で暮らす"

    def test_locked_active_rejected_by_goal_outcome_only_also_traces(self) -> None:
        """goal_update を伴わない goal_outcome だけの清算試行も、locked 拒否と

        同じ trace を残す (attempted_goal_text は None)。"""
        store = InMemoryGoalJournalStore()
        store.add_by_being(
            _BEING, _goal("g0", "山頂で狼煙を上げる", locked=True, origin=GOAL_ORIGIN_SCENARIO)
        )
        trace = _FakeTrace()
        applier, store, obs = _make(store=store, tick=7, trace=trace)

        result = applier.apply(
            _BEING, _PLAYER, goal_update_text=None, goal_outcome="achieved"
        )

        assert result is None
        rejected = [
            (kind, payload)
            for kind, payload in trace.records
            if kind == TraceEventKind.GOAL_REVISION_REJECTED
        ]
        assert len(rejected) == 1
        assert rejected[0][1]["attempted_goal_text"] is None

    def test_locked_rejection_trace_truncates_long_attempted_text(self) -> None:
        """attempted_goal_text は長すぎる場合に切り詰めて payload に載る。"""
        store = InMemoryGoalJournalStore()
        store.add_by_being(
            _BEING, _goal("g0", "山頂で狼煙を上げる", locked=True, origin=GOAL_ORIGIN_SCENARIO)
        )
        trace = _FakeTrace()
        applier, store, obs = _make(store=store, trace=trace)
        long_text = "あ" * (SELF_AUTHORED_GOAL_TEXT_MAX_CHARS)

        applier.apply(_BEING, _PLAYER, goal_update_text=long_text, goal_outcome=None)

        rejected = [
            payload
            for kind, payload in trace.records
            if kind == TraceEventKind.GOAL_REVISION_REJECTED
        ]
        assert len(rejected[0]["attempted_goal_text"]) <= 120

    def test_locked_rejection_without_trace_recorder_does_not_raise(self) -> None:
        """trace_recorder_provider 未配線でも拒否自体 (observation) は動く。"""
        store = InMemoryGoalJournalStore()
        store.add_by_being(
            _BEING, _goal("g0", "山頂で狼煙を上げる", locked=True, origin=GOAL_ORIGIN_SCENARIO)
        )
        applier, store, obs = _make(store=store)

        result = applier.apply(
            _BEING, _PLAYER, goal_update_text="この島で暮らす", goal_outcome=None
        )

        assert result is None
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

    def test_over_limit_goal_update_text_aborts_before_settling(self) -> None:
        """新目的の text が入口の上限を超えるとき、清算前に拒否され部分コミットにならない。

        SELF_AUTHORED_GOAL_TEXT_MAX_CHARS 超の text は GoalEntry を構築する前に
        (store に触れる前に) 観測付きで拒否される。これにより「旧目的を閉じて
        達成 evidence まで残したのに次の目的が立たない」部分コミット
        (silent failure) を防ぐ。旧目的は active のまま・転記も無し。

        (HIGH-1 回帰対応で GoalEntry VO 自体の上限は 2000 字まで緩めたため、
        以前はここで GoalEntryValidationException が飛んでいたが、いまは
        GoalRevisionApplier の事前チェックが観測を返して no-op に畳む)
        """
        store = InMemoryGoalJournalStore()
        store.add_by_being(
            _BEING, _goal("g1", "古い地図を手に入れる", locked=False, origin=GOAL_ORIGIN_SELF)
        )
        transcriber = _FakeSettlementTranscriber()
        applier, store, obs = _make(store=store, transcriber=transcriber)

        too_long = "あ" * (SELF_AUTHORED_GOAL_TEXT_MAX_CHARS + 1)
        result = applier.apply(
            _BEING, _PLAYER, goal_update_text=too_long, goal_outcome="achieved"
        )

        assert result is None
        # 旧目的は閉じられていない (active のまま)、転記も起きていない。
        assert store.get_active_by_being(_BEING).goal_id == "g1"
        assert store.get_active_by_being(_BEING).status == GOAL_STATUS_ACTIVE
        assert transcriber.calls == []
        assert obs == [(_PLAYER, GOAL_UPDATE_TEXT_TOO_LONG_OBSERVATION)]


class TestGoalUpdateTextLengthLimit:
    """HIGH-1 回帰対応: goal_update の入口 (SELF_AUTHORED_GOAL_TEXT_MAX_CHARS)。

    VO (GoalEntry) 自体の上限は 2000 字 (健全性の上限) まで緩めたため、
    「エージェント自筆の目的は短い命題であるべき」という制約は
    GoalRevisionApplier のこの事前チェックが守る。
    """

    def test_over_limit_text_is_rejected_and_existing_goal_unchanged(self) -> None:
        """201 字の goal_update は拒否され、既存目的は変わらず観測が返る。"""
        store = InMemoryGoalJournalStore()
        store.add_by_being(
            _BEING, _goal("g1", "魚を分けてもらう", locked=False, origin=GOAL_ORIGIN_SELF)
        )
        applier, store, obs = _make(store=store)

        too_long = "あ" * (SELF_AUTHORED_GOAL_TEXT_MAX_CHARS + 1)
        result = applier.apply(
            _BEING, _PLAYER, goal_update_text=too_long, goal_outcome=None
        )

        assert result is None
        active = store.get_active_by_being(_BEING)
        assert active.goal_id == "g1"  # 既存目的は書き換わっていない
        assert active.text == "魚を分けてもらう"
        assert obs == [(_PLAYER, GOAL_UPDATE_TEXT_TOO_LONG_OBSERVATION)]

    def test_over_limit_text_without_existing_goal_stays_noop(self) -> None:
        """active 目的が無いときも、201 字の goal_update は store に何も積まない。"""
        applier, store, obs = _make()

        too_long = "あ" * (SELF_AUTHORED_GOAL_TEXT_MAX_CHARS + 1)
        result = applier.apply(
            _BEING, _PLAYER, goal_update_text=too_long, goal_outcome=None
        )

        assert result is None
        assert store.list_all_by_being(_BEING) == []
        assert obs == [(_PLAYER, GOAL_UPDATE_TEXT_TOO_LONG_OBSERVATION)]

    def test_text_at_limit_is_accepted(self) -> None:
        """SELF_AUTHORED_GOAL_TEXT_MAX_CHARS ちょうどの長さは拒否されない (境界値)。"""
        applier, store, obs = _make()

        at_limit = "あ" * SELF_AUTHORED_GOAL_TEXT_MAX_CHARS
        result = applier.apply(
            _BEING, _PLAYER, goal_update_text=at_limit, goal_outcome=None
        )

        assert result is not None
        assert result.text == at_limit
        assert obs == []
