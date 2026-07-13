"""BeliefEvidence バッファ用の in-memory ストア実装。

U2 (証拠台帳統一設計)。``InMemoryEpisodicRecallBufferStore``
(``in_memory_episodic_reinterpretation_stores.py``) と同型の Being ごとの
list 保持。

横断レビュー H-3/M2 で thread-safe 化: ThreadPool の chunk 補完ワーカー
(``episodic_subjective_completion_schedulers.py``) が ``append_by_being``
で書く一方、メイン thread は固着 flush (``belief_consolidation_coordinator``)
で ``list_all_by_being`` → ``remove_by_being`` の read-modify-write を行う。
lock なしだと ``remove_by_being`` が「list 再構築 → 差し替え」する短い窓に
ワーカーが append すると evidence が無音で消える。#309 の
``InMemorySubjectiveEpisodeStore`` と同じ ``threading.RLock`` パターンを踏襲
する。
"""

from __future__ import annotations

import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable

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
        # ワーカー thread (append) とメイン thread (list → remove の
        # read-modify-write) が同じ dict / list を触るため、公開メソッド全体を
        # 1 つの RLock で保護する (#309 と同じ粒度・同じ理由)。
        self._lock = threading.RLock()

    def append_by_being(self, being_id: BeingId, evidence: BeliefEvidence) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(evidence, BeliefEvidence):
            raise TypeError("evidence must be BeliefEvidence")
        with self._lock:
            self._evidences[being_id].append(evidence)

    def list_all_by_being(self, being_id: BeingId) -> list[BeliefEvidence]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        with self._lock:
            rows = list(self._evidences.get(being_id, ()))
        return sorted(
            rows, key=lambda e: (_dt_key(e.occurred_at), e.evidence_id)
        )

    def remove_by_being(
        self, being_id: BeingId, evidence_ids: Iterable[str]
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        ids_to_remove = {str(eid) for eid in evidence_ids}
        if not ids_to_remove:
            return
        with self._lock:
            remaining = [
                e
                for e in self._evidences.get(being_id, ())
                if e.evidence_id not in ids_to_remove
            ]
            self._evidences[being_id] = remaining

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
        with self._lock:
            self._evidences[being_id] = list(evidences)


__all__ = ["InMemoryBeliefEvidenceBufferStore"]
