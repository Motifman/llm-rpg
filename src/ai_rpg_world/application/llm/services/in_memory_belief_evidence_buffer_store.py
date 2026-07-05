"""BeliefEvidence バッファ用の in-memory ストア実装。

U2 (証拠台帳統一設計)。``InMemoryEpisodicRecallBufferStore``
(``in_memory_episodic_reinterpretation_stores.py``) と同型の Being ごとの
list 保持。
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.semantic.repository.belief_evidence_buffer_repository import (
    BeliefEvidenceBufferRepository,
)
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
    BeliefEvidence,
)


def _dt_key(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class InMemoryBeliefEvidenceBufferStore(BeliefEvidenceBufferRepository):
    """Being ごとに ``BeliefEvidence`` の list を保持する。"""

    def __init__(self) -> None:
        self._evidences: dict[BeingId, list[BeliefEvidence]] = defaultdict(list)

    def append_by_being(self, being_id: BeingId, evidence: BeliefEvidence) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(evidence, BeliefEvidence):
            raise TypeError("evidence must be BeliefEvidence")
        self._evidences[being_id].append(evidence)

    def list_all_by_being(self, being_id: BeingId) -> list[BeliefEvidence]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        rows = list(self._evidences.get(being_id, ()))
        return sorted(
            rows, key=lambda e: (_dt_key(e.occurred_at), e.evidence_id)
        )

    def replace_all_by_being(
        self,
        being_id: BeingId,
        evidences: list[BeliefEvidence],
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(evidences, list):
            raise TypeError("evidences must be list")
        for e in evidences:
            if not isinstance(e, BeliefEvidence):
                raise TypeError("evidences elements must be BeliefEvidence")
        self._evidences[being_id] = list(evidences)


__all__ = ["InMemoryBeliefEvidenceBufferStore"]
