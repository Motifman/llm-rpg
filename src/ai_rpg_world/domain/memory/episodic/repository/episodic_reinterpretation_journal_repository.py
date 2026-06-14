"""EpisodicReinterpretationJournalRepository — 再解釈履歴の保管庫 interface。

DDD 再編 (Issue #470 Phase 1 PR5): 元
``application/llm/contracts/episodic_reinterpretation.py::EpisodicReinterpretationJournalRepository``
を domain に昇格し、``*Repository`` 命名に統一。

Phase 3 Step 3d-3 (Issue #470): legacy player_id 版 API (3 method) を撤去し、
being_id 版のみを残した。caller は全て ``*_by_being`` 経路で読み書きする。
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_entry import (
    EpisodicReinterpretationEntry,
)


class EpisodicReinterpretationJournalRepository(ABC):
    """再解釈履歴を保持し、最新 active entry だけを通常参照へ出すストア。

    一次キーは ``BeingId``。
    """

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
        """being_id keyed で active entry を返す。なければ None。"""

    @abstractmethod
    def list_by_episode_by_being(
        self,
        being_id: BeingId,
        episode_id: str,
    ) -> list[EpisodicReinterpretationEntry]:
        """being_id keyed で履歴を新しい順に返す。"""


__all__ = ["EpisodicReinterpretationJournalRepository"]
