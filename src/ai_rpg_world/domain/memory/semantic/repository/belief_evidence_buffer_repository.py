"""BeliefEvidenceBufferRepository — 証拠バッファの保管庫 interface。

U2 (証拠台帳統一設計): 固着パス (belief journal への統合、U3) が周期的に
drain するまでの間、``BeliefEvidence`` を Being ごとに溜めておくバッファ。
``EpisodicReinterpretationJournalRepository`` / ``episodic_recall_buffer``
系と同型の per-Being store (一次キーは ``BeingId``)。

U3b (固着 coordinator): ``remove_by_being`` を追加した。固着パス
(``BeliefConsolidationCoordinator``) が 1 batch を処理し終えた evidence を
buffer から取り除くための drain 操作。U2 時点では「証拠が観測可能に溜まる」
ことだけが目的だったため未導入だったが、固着パス本体が evidence を消費する
ようになったので、処理済みの evidence を再処理しないための除去 API が要る。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Iterable

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

        snapshot capture / 固着パス drain の両方から使う enumeration。
        """

    @abstractmethod
    def remove_by_being(
        self, being_id: BeingId, evidence_ids: Iterable[str]
    ) -> None:
        """being_id 配下から ``evidence_ids`` に一致する evidence を取り除く。

        U3b (固着 coordinator): 1 batch を処理し終えた evidence を buffer から
        drain するための操作。存在しない evidence_id は無視する (無条件失敗
        にしない、既存 store の ``mark_processed_by_being`` 系と同じ規約)。
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
