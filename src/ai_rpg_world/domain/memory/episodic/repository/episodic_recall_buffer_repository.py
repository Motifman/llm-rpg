"""EpisodicRecallBufferRepository — 想起イベントを再解釈 flush まで保持するリポジトリ。

DDD 再編 (Issue #470 Phase 1 PR5): 元
``application/llm/contracts/episodic_reinterpretation.py::IEpisodicRecallBufferStore``
を domain に昇格し、``*Repository`` 命名に統一。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

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


# 後方互換: 旧名 ``IEpisodicRecallBufferStore`` は本 Repository の alias。
IEpisodicRecallBufferStore = EpisodicRecallBufferRepository

__all__ = ["EpisodicRecallBufferRepository", "IEpisodicRecallBufferStore"]
