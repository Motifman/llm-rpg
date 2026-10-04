"""SqliteBeliefEvidenceBufferStore の roundtrip 検証。

sqlite_episodic_reinterpretation_store の既存テストと同じ規約:
close → reopen で永続化されていることを確認する (snapshot restore と
同じ「別プロセス再開」を模した検証)。
"""

from __future__ import annotations

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

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
    _payload_to_evidence,
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
        observed_turn=0,
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
                observed_turn=0,
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

    def test_in_context_belief_ids_persists_across_reconnect(self) -> None:
        """U4 で追加された in_context_belief_ids が close → reopen 後も空に
        落ちず元の belief_id 群のまま戻る (M1 再発防止)。"""
        being_id = BeingId("being_w1_p1")
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "belief_evidence.db")
            store = SqliteBeliefEvidenceBufferStore.connect(path)
            evidence = BeliefEvidence(
                evidence_id="e1",
                source_kind=BeliefEvidenceSourceKind.PREDICTION_ERROR,
                episode_ids=("ep-1",),
                cue_signature="tool:explore|spot:3",
                text="探索は空振りだった",
                salience=BELIEF_EVIDENCE_SALIENCE_LOW,
                occurred_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                in_context_belief_ids=("belief-1", "belief-2"),
                observed_turn=0,
            )
            store.append_by_being(being_id, evidence)
            del store

            reopened = SqliteBeliefEvidenceBufferStore.connect(path)
            restored = reopened.list_all_by_being(being_id)[0]
            assert restored.in_context_belief_ids == ("belief-1", "belief-2")


class TestSqliteBeliefEvidenceFullFieldRoundtripContract:
    """全フィールドに非 default 値を入れた evidence が保存 → 読み出しで完全一致して戻る契約テスト。

    ``BeliefEvidence`` にフィールドが増えたのに payload codec
    (``_evidence_to_payload`` / ``_payload_to_evidence``) が追従しないと、非
    default 値が往復で default に落ちて ``==`` が破れ、このテストが自動で赤に
    なる。今回の M1 (in_context_belief_ids の追従漏れ) と同型の silent failure を
    将来も構造で検出するための守り。
    """

    def _full_evidence(self) -> BeliefEvidence:
        return BeliefEvidence(
            evidence_id="e-full",
            source_kind=BeliefEvidenceSourceKind.HEARSAY,
            episode_ids=("ep-1", "ep-2"),
            cue_signature="tool:gather|spot:5",
            text="全フィールドを非 default 値で埋めた証拠",
            salience=BELIEF_EVIDENCE_SALIENCE_HIGH,
            occurred_at=datetime(2026, 7, 1, 12, 30, 45, 123456, tzinfo=timezone.utc),
            observed_turn=17,
            tick=42,
            in_context_belief_ids=("belief-1", "belief-2"),
            source_speaker="noah",
            what_happened=("浜に流木は無かった", "ノア「波が運んでくる」"),
        )

    def test_all_round_trips_exactly(self) -> None:
        """append_by_being → close → reopen → list_all_by_being の往復で
        evidence が元と完全一致する。"""
        being_id = BeingId("being_w1_p1")
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "belief_evidence.db")
            store = SqliteBeliefEvidenceBufferStore.connect(path)
            evidence = self._full_evidence()
            store.append_by_being(being_id, evidence)
            del store

            reopened = SqliteBeliefEvidenceBufferStore.connect(path)
            restored = reopened.list_all_by_being(being_id)[0]
            assert restored == evidence

    def test_replace_all_being_all_round_trips_exactly(self) -> None:
        """replace_all_by_being 経路でも evidence が元と完全一致する。"""
        being_id = BeingId("being_w1_p1")
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "belief_evidence.db")
            store = SqliteBeliefEvidenceBufferStore.connect(path)
            evidence = self._full_evidence()
            store.replace_all_by_being(being_id, [evidence])

            restored = store.list_all_by_being(being_id)[0]
            assert restored == evidence


class TestSqliteBeliefEvidenceWhatHappenedPayload:
    """SQLite の行の what_happened (#1509) を、キーが無ければ空として読み、形の崩れた値は作り直さずに拒む挙動を保証する。"""

    _BASE = {
        "evidence_id": "e-1",
        "source_kind": "prediction_error",
        "episode_ids": ["exp-1"],
        "cue_signature": "expectation:miss",
        "text": "外れた",
        "salience": "low",
        "occurred_at": "2026-10-04T00:00:00+00:00",
        "observed_turn": 3,
    }

    def test_row_without_what_happened_reads_empty(self) -> None:
        """#1509 より前に書かれた (キーの無い) 行は、時系列の無い材料として読む。"""
        evidence = _payload_to_evidence(dict(self._BASE))

        assert evidence.what_happened == ()

    @pytest.mark.parametrize("value", ["浜", [None], None], ids=["str", "none_item", "none"])
    def test_malformed_what_happened_is_rejected(self, value: object) -> None:
        """what_happened が list[str] でない行は、1 文字ずつの行や "None" の行に化けさせずに ValueError で拒む。"""
        with pytest.raises(ValueError, match="what_happened"):
            _payload_to_evidence({**self._BASE, "what_happened": value})
