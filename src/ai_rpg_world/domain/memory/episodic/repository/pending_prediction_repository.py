"""PendingPredictionRepository — 保留中の予測 (約束) の per-Being 保管庫 interface。

U10a (予測誤差統一設計 部品6): ``BeliefEvidenceBufferRepository`` /
``EpisodicRecallBufferRepository`` と同型の per-Being store (一次キーは
``BeingId``)。容量上限 (既定 8 件) を超えたら最も古いものから evict する
(= 「約束を溜め込みすぎない」ための構造的な歯止め。清算・期限失効は U10b の
スコープ)。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.pending_prediction import (
    PendingPrediction,
)

PENDING_PREDICTION_DEFAULT_CAP = 8


class PendingPredictionRepository(ABC):
    """保留中の予測を保持する。一次キーは ``BeingId``。"""

    @abstractmethod
    def add_by_being(self, being_id: BeingId, pending: PendingPrediction) -> None:
        """being_id keyed で pending prediction を 1 件追加する。

        既存件数が容量上限 (``PENDING_PREDICTION_DEFAULT_CAP``) に達している
        場合は、追加前に最も古い (= ``created_tick`` が最小、同値なら
        追加順が先の) 1 件を evict する。
        """

    @abstractmethod
    def list_all_by_being(self, being_id: BeingId) -> list[PendingPrediction]:
        """being_id keyed で全 pending prediction を追加順で返す。

        snapshot capture / prompt build 時の再浮上判定の両方から使う
        enumeration。
        """

    @abstractmethod
    def replace_all_by_being(
        self,
        being_id: BeingId,
        predictions: list[PendingPrediction],
    ) -> None:
        """being_id 配下の pending prediction を ``predictions`` で完全置換する。

        snapshot restore primitive。Snapshot 経路以外からの呼び出しは
        想定しない (``BeliefEvidenceBufferRepository.replace_all_by_being``
        と同じ規約)。
        """


__all__ = ["PendingPredictionRepository", "PENDING_PREDICTION_DEFAULT_CAP"]
