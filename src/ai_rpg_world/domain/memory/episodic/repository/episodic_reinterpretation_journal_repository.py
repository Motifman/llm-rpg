"""EpisodicReinterpretationJournalRepository — 再解釈履歴の保管庫 interface。

DDD 再編 (Issue #470 Phase 1 PR5): 元
``application/llm/contracts/episodic_reinterpretation.py::IEpisodicReinterpretationJournalStore``
を domain に昇格し、``*Repository`` 命名に統一。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_entry import (
    EpisodicReinterpretationEntry,
)


class EpisodicReinterpretationJournalRepository(ABC):
    """再解釈履歴を保持し、最新 active entry だけを通常参照へ出すストア。"""

    @abstractmethod
    def put_active(self, entry: EpisodicReinterpretationEntry) -> None:
        """同一 episode の既存 active entry を supersede して entry を active 保存する。"""

    @abstractmethod
    def get_active(
        self,
        player_id: int,
        episode_id: str,
    ) -> EpisodicReinterpretationEntry | None:
        """通常参照用の active entry を返す。なければ None。"""

    @abstractmethod
    def list_by_episode(
        self,
        player_id: int,
        episode_id: str,
    ) -> list[EpisodicReinterpretationEntry]:
        """監査用に履歴を新しい順で返す。"""


# 後方互換: 旧名 ``IEpisodicReinterpretationJournalStore`` は本 Repository の alias。
IEpisodicReinterpretationJournalStore = EpisodicReinterpretationJournalRepository

__all__ = [
    "EpisodicReinterpretationJournalRepository",
    "IEpisodicReinterpretationJournalStore",
]
