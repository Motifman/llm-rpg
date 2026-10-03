"""証拠バッファが、予期の出来事から作った材料を出来事の ID ごとに 1 回だけ受け取る挙動を、全実装で保証する。"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timezone

import pytest

from ai_rpg_world.application.llm.services.in_memory_belief_evidence_buffer_store import (
    InMemoryBeliefEvidenceBufferStore,
)
from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.semantic.repository.belief_evidence_buffer_repository import (
    BeliefEvidenceBufferRepository,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
    BELIEF_EVIDENCE_SALIENCE_LOW,
    BeliefEvidence,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence_source_kind import (
    BeliefEvidenceSourceKind,
)
from ai_rpg_world.infrastructure.repository.sqlite_belief_evidence_buffer_store import (
    SqliteBeliefEvidenceBufferStore,
)

BEING = BeingId("being-rio")
OTHER = BeingId("being-kai")


def _in_memory() -> BeliefEvidenceBufferRepository:
    return InMemoryBeliefEvidenceBufferStore()


def _sqlite() -> BeliefEvidenceBufferRepository:
    return SqliteBeliefEvidenceBufferStore(sqlite3.connect(":memory:"))


STORES: list[Callable[[], BeliefEvidenceBufferRepository]] = [_in_memory, _sqlite]


def _evidence(evidence_id: str = "belief-evidence-exp-1@3") -> BeliefEvidence:
    return BeliefEvidence(
        evidence_id=evidence_id,
        source_kind=BeliefEvidenceSourceKind.PREDICTION_ERROR,
        episode_ids=("exp-1",),
        cue_signature="expectation:miss",
        text="たぶんと思っていた予期「箱は空だろう」は外れた。",
        salience=BELIEF_EVIDENCE_SALIENCE_LOW,
        occurred_at=datetime(2026, 10, 3, tzinfo=timezone.utc),
        observed_turn=3,
    )


@pytest.mark.parametrize("make_store", STORES)
class TestAppendReceived:
    """``append_received_by_being`` が材料と受け取り済みの ID を 1 回の呼び出しで書く挙動を保証する。"""

    def test_first_receipt_appends_evidence_and_returns_true(
        self, make_store: Callable[[], BeliefEvidenceBufferRepository]
    ) -> None:
        """初めての出来事の ID なら材料を積み、True を返し、ID を受け取り済みにする。"""
        store = make_store()

        appended = store.append_received_by_being(BEING, _evidence(), event_id="exp-1@3")

        assert appended is True
        assert [e.evidence_id for e in store.list_all_by_being(BEING)] == [
            "belief-evidence-exp-1@3"
        ]
        assert store.list_received_event_ids_by_being(BEING) == ["exp-1@3"]

    def test_same_event_id_twice_keeps_single_evidence(
        self, make_store: Callable[[], BeliefEvidenceBufferRepository]
    ) -> None:
        """同じ出来事の ID を二度受け取ると、2 回目は何も積まずに False を返す。"""
        store = make_store()
        store.append_received_by_being(BEING, _evidence(), event_id="exp-1@3")

        appended = store.append_received_by_being(BEING, _evidence(), event_id="exp-1@3")

        assert appended is False
        assert len(store.list_all_by_being(BEING)) == 1

    def test_receipt_survives_after_consolidation_drains_evidence(
        self, make_store: Callable[[], BeliefEvidenceBufferRepository]
    ) -> None:
        """固着が材料を取り除いたあとに同じ出来事が届いても、材料を積み直さない。"""
        store = make_store()
        store.append_received_by_being(BEING, _evidence(), event_id="exp-1@3")
        store.remove_by_being(BEING, ["belief-evidence-exp-1@3"])

        appended = store.append_received_by_being(BEING, _evidence(), event_id="exp-1@3")

        assert appended is False
        assert store.list_all_by_being(BEING) == []

    def test_receipts_are_scoped_by_being(
        self, make_store: Callable[[], BeliefEvidenceBufferRepository]
    ) -> None:
        """別の Being が同じ ID を受け取っていても、自分の受け取りは妨げられない。"""
        store = make_store()
        store.append_received_by_being(OTHER, _evidence(), event_id="exp-1@3")

        appended = store.append_received_by_being(BEING, _evidence(), event_id="exp-1@3")

        assert appended is True
        assert store.list_received_event_ids_by_being(BEING) == ["exp-1@3"]

    def test_replace_received_event_ids_restores_receipts(
        self, make_store: Callable[[], BeliefEvidenceBufferRepository]
    ) -> None:
        """snapshot から受け取り済みの ID を戻すと、その出来事はもう積まれず、戻さなかった ID は消える。"""
        store = make_store()
        store.append_received_by_being(BEING, _evidence("old"), event_id="exp-0@1")

        store.replace_received_event_ids_by_being(BEING, ["exp-1@3"])

        assert store.list_received_event_ids_by_being(BEING) == ["exp-1@3"]
        assert (
            store.append_received_by_being(BEING, _evidence(), event_id="exp-1@3")
            is False
        )
