"""EpisodicRecallBufferRepository — 想起イベントを再解釈 flush まで保持するリポジトリ。

DDD 再編 (Issue #470 Phase 1 PR5): 元
``application/llm/contracts/episodic_reinterpretation.py::EpisodicRecallBufferRepository``
を domain に昇格し、``*Repository`` 命名に統一。

Phase 3 Step 3d-1 (Issue #470): ``*_by_being`` API を並走追加。Step 3d-2 で
caller を新 API に切替え、Step 3d-3 で旧 player_id 版を撤去する想定。
並走期間中は両 API のデータは互いに見えない (= 同一 caller が新旧を
混在させない前提)。memo / semantic / memory_link と同じパターン。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episodic_recall_observation import (
    EpisodicRecallObservation,
)


class EpisodicRecallBufferRepository(ABC):
    """想起イベントを再解釈 flush まで保持するストア。"""

    @abstractmethod
    def append(self, observation: EpisodicRecallObservation) -> None:
        """想起観測を追加する。"""

    @abstractmethod
    def peek_batch(
        self,
        player_id: int,
        *,
        batch_size: int,
        max_contexts_per_episode: int,
    ) -> tuple[EpisodicRecallObservation, ...]:
        """episode ごとに束ねた pending batch を返す。削除はしない。"""

    @abstractmethod
    def mark_processed(self, player_id: int, recall_ids: tuple[str, ...]) -> None:
        """処理済み recall_id を pending から除く。"""

    @abstractmethod
    def pending_count(self, player_id: int) -> int:
        """指定 player の pending 件数。"""

    # ===== Phase 3 Step 3d-1: being_id 版を並走追加 =====

    @abstractmethod
    def append_by_being(
        self, being_id: BeingId, observation: EpisodicRecallObservation
    ) -> None:
        """being_id keyed で observation を追加する。

        observation.player_id は attach 元 PlayerId として保持されるが、本 API
        では BeingId が一次キーとして扱われる。
        """

    @abstractmethod
    def peek_batch_by_being(
        self,
        being_id: BeingId,
        *,
        batch_size: int,
        max_contexts_per_episode: int,
    ) -> tuple[EpisodicRecallObservation, ...]:
        """being_id keyed で pending batch を返す。"""

    @abstractmethod
    def mark_processed_by_being(
        self, being_id: BeingId, recall_ids: tuple[str, ...]
    ) -> None:
        """being_id keyed で処理済み recall_id を pending から除く。"""

    @abstractmethod
    def pending_count_by_being(self, being_id: BeingId) -> int:
        """being_id keyed で pending 件数を返す。"""


__all__ = ["EpisodicRecallBufferRepository"]
