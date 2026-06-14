"""MemoryLinkRepository — エピソード記憶リンクの保管庫 interface。

DDD 再編 (Issue #470 Phase 1 PR5): 元
``application/llm/contracts/episodic_memory_link_store_port.py::MemoryLinkRepository``
を domain に昇格し、``*Repository`` 命名に統一。

Phase 3 Step 3c-3 (Issue #470): legacy player_id 版 API (7 method) を撤去し、
being_id 版のみを残した。caller は全て ``*_by_being`` 経路で読み書きする
(Step 3c-2 で caller 切替済)。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import (
    MemoryLink,
    MemoryLinkType,
)


class MemoryLinkRepository(ABC):
    """エピソード間リンクを保持する。

    一次キーは ``BeingId``。run 跨ぎ identity を保つため Being 集約を識別子に
    使う設計 (Phase 2 で導入、Phase 3 で全 caller を Being keyed に統一)。
    """

    @abstractmethod
    def upsert_link_by_being(self, being_id: BeingId, link: MemoryLink) -> None:
        """being_id keyed で link を upsert する。

        link.player_id は attach 元 PlayerId として保持されるが、本 API では
        BeingId が一次キー。同一 (being_id, episode_id_a, episode_id_b,
        link_type) は上書き。
        """

    @abstractmethod
    def get_link_by_being(
        self,
        being_id: BeingId,
        episode_id_a: str,
        episode_id_b: str,
        link_type: MemoryLinkType,
    ) -> MemoryLink | None:
        """being_id keyed で link を引く。正規化済みの a,b で検索。"""

    @abstractmethod
    def list_links_for_episode_by_being(
        self,
        being_id: BeingId,
        episode_id: str,
        *,
        now: datetime,
        limit: int,
    ) -> list[MemoryLink]:
        """being_id keyed で episode に接続するリンクを返す (件数上限付き)。"""

    @abstractmethod
    def list_all_incident_links_by_being(
        self,
        being_id: BeingId,
        episode_id: str,
        *,
        now: datetime,
    ) -> list[MemoryLink]:
        """being_id keyed で episode に接続する全リンク (件数上限なし)。"""

    @abstractmethod
    def count_links_for_episode_by_being(
        self, being_id: BeingId, episode_id: str
    ) -> int:
        """being_id keyed で接続リンク数を返す。"""

    @abstractmethod
    def remove_weakest_link_for_episode_by_being(
        self,
        being_id: BeingId,
        episode_id: str,
        *,
        now: datetime,
    ) -> bool:
        """being_id keyed で最弱リンクを 1 件削除。削除したら True。"""

    @abstractmethod
    def list_all_links_for_being(self, being_id: BeingId) -> list[MemoryLink]:
        """being_id keyed で全リンク一覧を返す。"""

    @abstractmethod
    def replace_all_by_being(
        self, being_id: BeingId, links: list[MemoryLink]
    ) -> None:
        """being_id 配下のリンクを ``links`` で完全置換する。

        Phase 4 Step 4-2a (Issue #470): snapshot restore primitive。**既存の
        being 配下リンクは全て削除** され、``links`` の通りに再構築される。
        Snapshot 経路以外からの呼び出しは想定しない。
        """


__all__ = ["MemoryLinkRepository"]
