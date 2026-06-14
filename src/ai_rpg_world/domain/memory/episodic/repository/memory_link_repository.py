"""MemoryLinkRepository — エピソード記憶リンクの保管庫 interface。

DDD 再編 (Issue #470 Phase 1 PR5): 元
``application/llm/contracts/episodic_memory_link_store_port.py::MemoryLinkRepository``
を domain に昇格し、``*Repository`` 命名に統一。

Phase 3 Step 3c-1 (Issue #470): ``*_by_being`` API を並走追加。Step 3c-2 で
caller を新 API に切替え、Step 3c-3 で旧 player_id 版を撤去する想定。
並走期間中は両 API のデータは互いに見えない (= 同一 caller が新旧を
混在させない前提)。memo / semantic の Step 3a / 3b と同じパターン。
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
    """プレイヤー単位で MemoryLink を保持する。"""

    @abstractmethod
    def upsert_link(self, link: MemoryLink) -> None:
        """同一 (player_id, episode_id_a, episode_id_b, link_type) は上書き（full replace）。"""

    @abstractmethod
    def get_link(
        self,
        player_id: int,
        episode_id_a: str,
        episode_id_b: str,
        link_type: MemoryLinkType,
    ) -> MemoryLink | None:
        """正規化済みの a,b で検索。"""

    @abstractmethod
    def list_links_for_episode(
        self,
        player_id: int,
        episode_id: str,
        *,
        now: datetime,
        limit: int,
    ) -> list[MemoryLink]:
        """episode_id に接続するリンクを返す（件数上限付き）。"""

    @abstractmethod
    def list_all_incident_links(
        self,
        player_id: int,
        episode_id: str,
        *,
        now: datetime,
    ) -> list[MemoryLink]:
        """episode_id に接続する全リンク（セマンティック昇格の部分グラフ展開用。件数上限なし）。"""

    @abstractmethod
    def count_links_for_episode(self, player_id: int, episode_id: str) -> int:
        """接続リンク数（上限判定用）。"""

    @abstractmethod
    def remove_weakest_link_for_episode(
        self,
        player_id: int,
        episode_id: str,
        *,
        now: datetime,
    ) -> bool:
        """実効強度が最も低いリンクを 1 件削除。削除したら True。"""

    @abstractmethod
    def list_all_links_for_player(self, player_id: int) -> list[MemoryLink]:
        """当該プレイヤーの全リンク（クラスタ検出・一括処理用）。"""

    # ===== Phase 3 Step 3c-1: being_id 版を並走追加 =====

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


__all__ = ["MemoryLinkRepository"]
