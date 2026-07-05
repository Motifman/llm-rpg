"""InMemoryBeliefEvidenceBufferStore の per-Being 挙動を保証する。"""

from __future__ import annotations

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
