"""BeliefEvidenceBufferRepository — 証拠バッファの保管庫 interface。

U2 (証拠台帳統一設計): 固着パス (belief journal への統合、U3) が周期的に
drain するまでの間、``BeliefEvidence`` を Being ごとに溜めておくバッファ。
``EpisodicReinterpretationJournalRepository`` / ``episodic_recall_buffer``
系と同型の per-Being store (一次キーは ``BeingId``)。

U2 時点では drain API (batch 取得 + mark_processed) は導入しない。固着パス
本体は U3 のスコープであり、本 PR は「証拠が観測可能に溜まる」ことだけを
保証する。将来の drain API は ``EpisodicRecallBufferRepository`` の
``peek_batch_by_being`` / ``mark_processed_by_being`` を型紙にする想定。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.semantic.value_object.belief_evidence import (
    BeliefEvidence,
)


class BeliefEvidenceBufferRepository(ABC):
    """証拠バッファを保持する。一次キーは ``BeingId``。"""

    @abstractmethod
    def append_by_being(self, being_id: BeingId, evidence: BeliefEvidence) -> None:
        """being_id keyed で evidence を 1 件追加する。"""

    @abstractmethod
    def list_all_by_being(self, being_id: BeingId) -> list[BeliefEvidence]:
        """being_id keyed で全 evidence を ``occurred_at`` 昇順で返す。

        snapshot capture / 将来の固着パス drain の両方から使う enumeration。
        """

    @abstractmethod
    def replace_all_by_being(
        self,
        being_id: BeingId,
        evidences: list[BeliefEvidence],
    ) -> None:
        """being_id 配下の evidence を ``evidences`` で完全置換する。

        snapshot restore primitive。Snapshot 経路以外からの呼び出しは
        想定しない (``EpisodicReinterpretationJournalRepository.replace_all_by_being``
        と同じ規約)。
        """


__all__ = ["BeliefEvidenceBufferRepository"]
