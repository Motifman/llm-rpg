"""SqliteBeliefEvidenceBufferStore の roundtrip 検証。

sqlite_episodic_reinterpretation_store の既存テストと同じ規約:
close → reopen で永続化されていることを確認する (snapshot restore と
同じ「別プロセス再開」を模した検証)。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import tempfile

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
    BELIEF_EVIDENCE_SALIENCE_HIGH,
    BELIEF_EVIDENCE_SALIENCE_LOW,
    BeliefEvidence,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)
from ai_rpg_world.infrastructure.repository.sqlite_belief_evidence_buffer_store import (
    SqliteBeliefEvidenceBufferStore,
)


def _evidence(evidence_id: str, *, tick: int | None = 10) -> BeliefEvidence:
    return BeliefEvidence(
        evidence_id=evidence_id,
        source_kind=BeliefEvidenceSourceKind.PREDICTION_ERROR,
        episode_ids=("ep-1", "ep-2"),
        cue_signature="tool:explore|spot:3",
        text="探索は空振りだった",
        salience=BELIEF_EVIDENCE_SALIENCE_LOW,
        occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        tick=tick,
    )


class TestSqliteBeliefEvidenceBufferStore:
    def test_append_persists_across_reconnect(self) -> None:
        being_id = BeingId("being_w1_p1")
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "belief_evidence.db")
            store = SqliteBeliefEvidenceBufferStore.connect(path)
            store.append_by_being(being_id, _evidence("e1"))
            del store

            reopened = SqliteBeliefEvidenceBufferStore.connect(path)
            rows = reopened.list_all_by_being(being_id)
            assert len(rows) == 1
            restored = rows[0]
            assert restored.evidence_id == "e1"
            assert restored.source_kind == BeliefEvidenceSourceKind.PREDICTION_ERROR
            assert restored.episode_ids == ("ep-1", "ep-2")
            assert restored.cue_signature == "tool:explore|spot:3"
            assert restored.salience == BELIEF_EVIDENCE_SALIENCE_LOW
            assert restored.tick == 10

    def test_roundtrip_preserves_null_tick(self) -> None:
        """tick=None (非同期補完で current_tick_provider が無い場合) が
        SQLite roundtrip で None のまま戻ることを保証する。"""
        being_id = BeingId("being_w1_p1")
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "belief_evidence.db")
            store = SqliteBeliefEvidenceBufferStore.connect(path)
            store.append_by_being(being_id, _evidence("e1", tick=None))

            rows = store.list_all_by_being(being_id)
            assert rows[0].tick is None

    def test_replace_all_by_being_overwrites_existing_rows(self) -> None:
        being_id = BeingId("being_w1_p1")
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "belief_evidence.db")
            store = SqliteBeliefEvidenceBufferStore.connect(path)
            store.append_by_being(being_id, _evidence("e1"))

            store.replace_all_by_being(
                being_id,
                [_evidence("e2", tick=20), _evidence("e3", tick=30)],
            )

            ids = [e.evidence_id for e in store.list_all_by_being(being_id)]
            assert ids == ["e2", "e3"]

    def test_high_salience_roundtrips(self) -> None:
        being_id = BeingId("being_w1_p1")
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "belief_evidence.db")
            store = SqliteBeliefEvidenceBufferStore.connect(path)
            evidence = BeliefEvidence(
                evidence_id="e-high",
                source_kind=BeliefEvidenceSourceKind.PREDICTION_ERROR,
                episode_ids=("ep-1",),
                cue_signature="tool:gather",
                text="重大な想定外だった",
                salience=BELIEF_EVIDENCE_SALIENCE_HIGH,
                occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            )
            store.append_by_being(being_id, evidence)

            rows = store.list_all_by_being(being_id)
            assert rows[0].salience == BELIEF_EVIDENCE_SALIENCE_HIGH

    def test_being_scopes_are_isolated(self) -> None:
        being_a = BeingId("being-a")
        being_b = BeingId("being-b")
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "belief_evidence.db")
            store = SqliteBeliefEvidenceBufferStore.connect(path)
            store.append_by_being(being_a, _evidence("e1"))

            assert store.list_all_by_being(being_b) == []
            assert len(store.list_all_by_being(being_a)) == 1

    def test_remove_by_being_removes_only_specified_ids_and_persists(self) -> None:
        """指定 evidence_id だけが削除され、reconnect 後も反映が残る。"""
        being_id = BeingId("being_w1_p1")
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "belief_evidence.db")
            store = SqliteBeliefEvidenceBufferStore.connect(path)
            store.append_by_being(being_id, _evidence("e1"))
            store.append_by_being(being_id, _evidence("e2"))
            store.append_by_being(being_id, _evidence("e3"))

            store.remove_by_being(being_id, ["e1", "e3"])
            del store

            reopened = SqliteBeliefEvidenceBufferStore.connect(path)
            ids = [e.evidence_id for e in reopened.list_all_by_being(being_id)]
            assert ids == ["e2"]

    def test_remove_by_being_ignores_unknown_ids(self) -> None:
        """存在しない evidence_id を渡しても例外にならない。"""
        being_id = BeingId("being_w1_p1")
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "belief_evidence.db")
            store = SqliteBeliefEvidenceBufferStore.connect(path)
            store.append_by_being(being_id, _evidence("e1"))

            store.remove_by_being(being_id, ["unknown-id"])

            ids = [e.evidence_id for e in store.list_all_by_being(being_id)]
            assert ids == ["e1"]
