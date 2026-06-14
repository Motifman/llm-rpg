"""EpisodicReinterpretationJournalRepository — 再解釈履歴の保管庫 interface。

DDD 再編 (Issue #470 Phase 1 PR5): 元
``application/llm/contracts/episodic_reinterpretation.py::EpisodicReinterpretationJournalRepository``
を domain に昇格し、``*Repository`` 命名に統一。

Phase 3 Step 3d-1 (Issue #470): ``*_by_being`` API を並走追加。Step 3d-2 で
caller を新 API に切替え、Step 3d-3 で旧 player_id 版を撤去する想定。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_rpg_world.domain.being.value_object.being_id import BeingId
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

    # ===== Phase 3 Step 3d-1: being_id 版を並走追加 =====

    @abstractmethod
    def put_active_by_being(
        self, being_id: BeingId, entry: EpisodicReinterpretationEntry
    ) -> None:
        """being_id keyed で active entry を保存する。同一 episode の既存
        active entry は supersede。"""

    @abstractmethod
    def get_active_by_being(
        self,
        being_id: BeingId,
        episode_id: str,
    ) -> EpisodicReinterpretationEntry | None:
        """being_id keyed で active entry を返す。"""

    @abstractmethod
    def list_by_episode_by_being(
        self,
        being_id: BeingId,
        episode_id: str,
    ) -> list[EpisodicReinterpretationEntry]:
        """being_id keyed で履歴を新しい順に返す。"""


__all__ = ["EpisodicReinterpretationJournalRepository"]
