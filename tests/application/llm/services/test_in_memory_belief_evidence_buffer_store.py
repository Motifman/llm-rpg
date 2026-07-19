"""InMemoryBeliefEvidenceBufferStore の per-Being 挙動を保証する。"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
    InMemoryBeliefEvidenceBufferStore,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
    BELIEF_EVIDENCE_SALIENCE_LOW,
    BeliefEvidence,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)


def _evidence(evidence_id: str, occurred_at: datetime) -> BeliefEvidence:
    return BeliefEvidence(
        evidence_id=evidence_id,
        source_kind=BeliefEvidenceSourceKind.PREDICTION_ERROR,
        episode_ids=("ep-1",),
        cue_signature="tool:explore",
        text="探索は空振りだった",
        salience=BELIEF_EVIDENCE_SALIENCE_LOW,
        occurred_at=occurred_at,
    )


class TestInMemoryBeliefEvidenceBufferStore:
    def test_append_and_list_all_by_being(self) -> None:
        store = InMemoryBeliefEvidenceBufferStore()
        being_id = BeingId("being-1")
        base = datetime(2026, 7, 1, tzinfo=timezone.utc)
        store.append_by_being(being_id, _evidence("e1", base))
        store.append_by_being(being_id, _evidence("e2", base + timedelta(minutes=1)))

        rows = store.list_all_by_being(being_id)
        assert [e.evidence_id for e in rows] == ["e1", "e2"]

    def test_being_scopes_are_isolated(self) -> None:
        """異なる Being の evidence は互いに見えない。"""
        store = InMemoryBeliefEvidenceBufferStore()
        being_a = BeingId("being-a")
        being_b = BeingId("being-b")
        base = datetime(2026, 7, 1, tzinfo=timezone.utc)
        store.append_by_being(being_a, _evidence("e1", base))

        assert store.list_all_by_being(being_b) == []
        assert len(store.list_all_by_being(being_a)) == 1

    def test_list_all_by_being_returns_empty_for_unknown_being(self) -> None:
        store = InMemoryBeliefEvidenceBufferStore()
        assert store.list_all_by_being(BeingId("unknown")) == []

    def test_replace_all_by_being_overwrites(self) -> None:
        store = InMemoryBeliefEvidenceBufferStore()
        being_id = BeingId("being-1")
        base = datetime(2026, 7, 1, tzinfo=timezone.utc)
        store.append_by_being(being_id, _evidence("e1", base))

        store.replace_all_by_being(being_id, [_evidence("e2", base)])

        rows = store.list_all_by_being(being_id)
        assert [e.evidence_id for e in rows] == ["e2"]

    def test_replace_all_by_being_with_empty_list_clears(self) -> None:
        store = InMemoryBeliefEvidenceBufferStore()
        being_id = BeingId("being-1")
        store.append_by_being(being_id, _evidence("e1", datetime(2026, 7, 1, tzinfo=timezone.utc)))

        store.replace_all_by_being(being_id, [])

        assert store.list_all_by_being(being_id) == []

    def test_remove_by_being_removes_only_specified_ids(self) -> None:
        """指定した evidence_id だけが除去され、他は残る (固着パスの batch drain 用)。"""
        store = InMemoryBeliefEvidenceBufferStore()
        being_id = BeingId("being-1")
        base = datetime(2026, 7, 1, tzinfo=timezone.utc)
        store.append_by_being(being_id, _evidence("e1", base))
        store.append_by_being(being_id, _evidence("e2", base + timedelta(minutes=1)))
        store.append_by_being(being_id, _evidence("e3", base + timedelta(minutes=2)))

        store.remove_by_being(being_id, ["e1", "e3"])

        rows = store.list_all_by_being(being_id)
        assert [e.evidence_id for e in rows] == ["e2"]

    def test_remove_by_being_ignores_unknown_ids(self) -> None:
        """存在しない evidence_id を渡しても例外にならない (無条件失敗にしない)。"""
        store = InMemoryBeliefEvidenceBufferStore()
        being_id = BeingId("being-1")
        store.append_by_being(being_id, _evidence("e1", datetime(2026, 7, 1, tzinfo=timezone.utc)))

        store.remove_by_being(being_id, ["unknown-id"])

        assert [e.evidence_id for e in store.list_all_by_being(being_id)] == ["e1"]

    def test_remove_by_being_on_unknown_being_is_noop(self) -> None:
        """未登録の being_id への remove も例外にならない。"""
        store = InMemoryBeliefEvidenceBufferStore()
        store.remove_by_being(BeingId("unknown"), ["e1"])


class TestInMemoryBeliefEvidenceBufferStoreThreadSafety:
    """横断レビュー H-3/M2: ThreadPool ワーカーとメイン thread の同時アクセス。"""

    def test_lock_is_reentrant_so_all_public_methods_work_while_held(self) -> None:
        """外側で ``_lock`` を保持したまま全公開メソッドを呼んでもデッドロックしない
        (RLock による再入可能性の確認)。"""
        store = InMemoryBeliefEvidenceBufferStore()
        being_id = BeingId("being-1")
        base = datetime(2026, 7, 1, tzinfo=timezone.utc)
        with store._lock:
            store.append_by_being(being_id, _evidence("e1", base))
            store.list_all_by_being(being_id)
            store.replace_all_by_being(being_id, [_evidence("e1", base)])
            store.remove_by_being(being_id, ["e1"])

    def test_concurrent_append_and_remove_never_loses_evidence(self) -> None:
        """ワーカー thread の ``append_by_being`` とメイン thread 相当の
        ``remove_by_being`` (list 再構築 → 差し替え) を並走させても、
        append した evidence が無音で消えない。

        ``remove_by_being`` は「存在しない id」を渡しても内部で
        list_all_by_being 相当の読み取り → 差し替えを行うため、この
        interleaving だけで元のバグ (H-3/M2) を再現できる。
        """
        store = InMemoryBeliefEvidenceBufferStore()
        being_id = BeingId("being-stress")
        base = datetime(2026, 7, 1, tzinfo=timezone.utc)
        total = 300

        def appender() -> None:
            for i in range(total):
                store.append_by_being(
                    being_id, _evidence(f"e{i}", base + timedelta(seconds=i))
                )

        def remover() -> None:
            for _ in range(total):
                # 存在しない id への remove でも内部で read-modify-write が
                # 走るため、これだけで append との競合窓を突く。
                store.remove_by_being(being_id, ["nonexistent-id"])

        t_append = threading.Thread(target=appender)
        t_remove = threading.Thread(target=remover)
        t_append.start()
        t_remove.start()
        t_append.join(timeout=10)
        t_remove.join(timeout=10)
        assert not t_append.is_alive()
        assert not t_remove.is_alive()

        rows = store.list_all_by_being(being_id)
        assert len(rows) == total
        assert {e.evidence_id for e in rows} == {f"e{i}" for i in range(total)}


class TestInMemoryBeliefEvidenceFullFieldRoundtripContract:
    """全フィールドに非 default 値を入れた evidence が保存 → 読み出しで完全一致して戻る契約テスト。

    SQLite 実装 (``TestSqliteBeliefEvidenceFullFieldRoundtripContract``) と対を
    なす。in-memory は codec を持たず参照をそのまま保持するので現状は自明に通るが、
    「保存経路が evidence を欠損させない」という store interface の契約を SQLite と
    同じ形で固定し、実装差を出さないための守り。
    """

    def _full_evidence(self) -> BeliefEvidence:
        return BeliefEvidence(
            evidence_id="e-full",
            source_kind=BeliefEvidenceSourceKind.HEARSAY,
            episode_ids=("ep-1", "ep-2"),
            cue_signature="tool:gather|spot:5",
            text="全フィールドを非 default 値で埋めた証拠",
            salience=BELIEF_EVIDENCE_SALIENCE_LOW,
            occurred_at=datetime(2026, 7, 1, 12, 30, 45, 123456, tzinfo=timezone.utc),
            tick=42,
            in_context_belief_ids=("belief-1", "belief-2"),
            source_speaker="noah",
        )

    def test_append_list_all_round_trips_exactly(self) -> None:
        """append_by_being → list_all_by_being の往復で evidence が元と完全一致する。"""
        store = InMemoryBeliefEvidenceBufferStore()
        being_id = BeingId("being-1")
        evidence = self._full_evidence()
        store.append_by_being(being_id, evidence)
        assert store.list_all_by_being(being_id)[0] == evidence

    def test_replace_all_being_all_round_trips_exactly(self) -> None:
        """replace_all_by_being → list_all_by_being の往復で evidence が元と完全一致する。"""
        store = InMemoryBeliefEvidenceBufferStore()
        being_id = BeingId("being-1")
        evidence = self._full_evidence()
        store.replace_all_by_being(being_id, [evidence])
        assert store.list_all_by_being(being_id)[0] == evidence
