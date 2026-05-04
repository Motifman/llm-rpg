"""エピソード記憶リンクの永続化ポート。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from ai_rpg_world.application.llm.contracts.episodic_memory_link import MemoryLink, MemoryLinkType


class IMemoryLinkStore(ABC):
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


__all__ = ["IMemoryLinkStore"]
