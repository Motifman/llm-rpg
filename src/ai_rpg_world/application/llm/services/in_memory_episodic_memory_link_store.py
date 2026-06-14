"""MemoryLinkRepository のインメモリ実装。

Phase 3 Step 3c-1 (Issue #470): being_id 版 API を並走追加。
内部に 2 つの独立した index を持つ:
- ``_by_key`` / ``_by_episode``: player_id 版 (= 旧 API、Step 3c-3 で撤去予定)
- ``_by_being_key`` / ``_by_being_episode``: being_id 版 (= 新 API)
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import DefaultDict, Dict, Set, Tuple

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.episodic.value_object.memory_link import (
    MemoryLink,
    MemoryLinkType,
    effective_link_strength,
    normalize_episode_pair,
)
from ai_rpg_world.domain.memory.episodic.repository.memory_link_repository import (
    MemoryLinkRepository,
)

LinkKey = Tuple[int, str, str, MemoryLinkType]
BeingLinkKey = Tuple[BeingId, str, str, MemoryLinkType]


def _key_for_link(link: MemoryLink) -> LinkKey:
    return (link.player_id, link.episode_id_a, link.episode_id_b, link.link_type)


def _being_key_for_link(being_id: BeingId, link: MemoryLink) -> BeingLinkKey:
    return (being_id, link.episode_id_a, link.episode_id_b, link.link_type)


class InMemoryMemoryLinkStore(MemoryLinkRepository):
    def __init__(self) -> None:
        self._by_key: Dict[LinkKey, MemoryLink] = {}
        self._by_episode: DefaultDict[int, DefaultDict[str, Set[LinkKey]]] = defaultdict(
            lambda: defaultdict(set)
        )
        # Phase 3 Step 3c-1: being_id 版並走 index
        self._by_being_key: Dict[BeingLinkKey, MemoryLink] = {}
        self._by_being_episode: DefaultDict[BeingId, DefaultDict[str, Set[BeingLinkKey]]] = defaultdict(
            lambda: defaultdict(set)
        )

    def _register_episode(self, player_id: int, episode_id: str, key: LinkKey) -> None:
        self._by_episode[player_id][episode_id].add(key)

    def _unregister_episode(self, player_id: int, episode_id: str, key: LinkKey) -> None:
        s = self._by_episode[player_id][episode_id]
        s.discard(key)
        if not s:
            del self._by_episode[player_id][episode_id]
        if not self._by_episode[player_id]:
            del self._by_episode[player_id]

    def upsert_link(self, link: MemoryLink) -> None:
        key = _key_for_link(link)
        old = self._by_key.get(key)
        if old is not None:
            self._unregister_episode(old.player_id, old.episode_id_a, key)
            self._unregister_episode(old.player_id, old.episode_id_b, key)
        self._by_key[key] = link
        self._register_episode(link.player_id, link.episode_id_a, key)
        self._register_episode(link.player_id, link.episode_id_b, key)

    def get_link(
        self,
        player_id: int,
        episode_id_a: str,
        episode_id_b: str,
        link_type: MemoryLinkType,
    ) -> MemoryLink | None:
        a, b = normalize_episode_pair(episode_id_a, episode_id_b)
        return self._by_key.get((player_id, a, b, link_type))

    def list_links_for_episode(
        self,
        player_id: int,
        episode_id: str,
        *,
        now: datetime,
        limit: int,
    ) -> list[MemoryLink]:
        if limit <= 0:
            return []
        eid = episode_id.strip()
        keys = self._by_episode.get(player_id, {}).get(eid, set())
        out: list[MemoryLink] = []
        for k in keys:
            link = self._by_key.get(k)
            if link is not None:
                out.append(link)
        out.sort(
            key=lambda ln: effective_link_strength(ln, now),
            reverse=True,
        )
        return out[:limit]

    def list_all_incident_links(
        self,
        player_id: int,
        episode_id: str,
        *,
        now: datetime,
    ) -> list[MemoryLink]:
        eid = episode_id.strip()
        keys = self._by_episode.get(player_id, {}).get(eid, set())
        out: list[MemoryLink] = []
        for k in keys:
            link = self._by_key.get(k)
            if link is not None:
                out.append(link)
        return out

    def count_links_for_episode(self, player_id: int, episode_id: str) -> int:
        eid = episode_id.strip()
        return len(self._by_episode.get(player_id, {}).get(eid, set()))

    def remove_weakest_link_for_episode(
        self,
        player_id: int,
        episode_id: str,
        *,
        now: datetime,
    ) -> bool:
        keys = list(self._by_episode.get(player_id, {}).get(episode_id.strip(), set()))
        if not keys:
            return False
        weakest_key = min(
            keys,
            key=lambda k: effective_link_strength(self._by_key[k], now),
        )
        link = self._by_key.pop(weakest_key, None)
        if link is None:
            return False
        self._unregister_episode(player_id, link.episode_id_a, weakest_key)
        self._unregister_episode(player_id, link.episode_id_b, weakest_key)
        return True

    def list_all_links_for_player(self, player_id: int) -> list[MemoryLink]:
        return [ln for ln in self._by_key.values() if ln.player_id == player_id]

    # ===== Phase 3 Step 3c-1: being_id 版を並走追加 =====

    def _register_being_episode(
        self, being_id: BeingId, episode_id: str, key: BeingLinkKey
    ) -> None:
        self._by_being_episode[being_id][episode_id].add(key)

    def _unregister_being_episode(
        self, being_id: BeingId, episode_id: str, key: BeingLinkKey
    ) -> None:
        s = self._by_being_episode[being_id][episode_id]
        s.discard(key)
        if not s:
            del self._by_being_episode[being_id][episode_id]
        if not self._by_being_episode[being_id]:
            del self._by_being_episode[being_id]

    def upsert_link_by_being(self, being_id: BeingId, link: MemoryLink) -> None:
        """being_id keyed で link を upsert する。

        ``link`` は ``MemoryLink`` VO であり、``__post_init__`` で
        ``normalize_episode_pair`` 済 (= ``a < b``) であることを前提とする。
        そのため key 生成・index 登録の側では再正規化しない (``get_link_by_being``
        は呼出側が生文字列を渡しうるため正規化する)。
        """
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(link, MemoryLink):
            raise TypeError("link must be MemoryLink")
        key = _being_key_for_link(being_id, link)
        old = self._by_being_key.get(key)
        if old is not None:
            self._unregister_being_episode(being_id, old.episode_id_a, key)
            self._unregister_being_episode(being_id, old.episode_id_b, key)
        self._by_being_key[key] = link
        self._register_being_episode(being_id, link.episode_id_a, key)
        self._register_being_episode(being_id, link.episode_id_b, key)

    def get_link_by_being(
        self,
        being_id: BeingId,
        episode_id_a: str,
        episode_id_b: str,
        link_type: MemoryLinkType,
    ) -> MemoryLink | None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        a, b = normalize_episode_pair(episode_id_a, episode_id_b)
        return self._by_being_key.get((being_id, a, b, link_type))

    def list_links_for_episode_by_being(
        self,
        being_id: BeingId,
        episode_id: str,
        *,
        now: datetime,
        limit: int,
    ) -> list[MemoryLink]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if limit <= 0:
            return []
        eid = episode_id.strip()
        keys = self._by_being_episode.get(being_id, {}).get(eid, set())
        out: list[MemoryLink] = []
        for k in keys:
            link = self._by_being_key.get(k)
            if link is not None:
                out.append(link)
        out.sort(
            key=lambda ln: effective_link_strength(ln, now),
            reverse=True,
        )
        return out[:limit]

    def list_all_incident_links_by_being(
        self,
        being_id: BeingId,
        episode_id: str,
        *,
        now: datetime,
    ) -> list[MemoryLink]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        eid = episode_id.strip()
        keys = self._by_being_episode.get(being_id, {}).get(eid, set())
        out: list[MemoryLink] = []
        for k in keys:
            link = self._by_being_key.get(k)
            if link is not None:
                out.append(link)
        return out

    def count_links_for_episode_by_being(
        self, being_id: BeingId, episode_id: str
    ) -> int:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        eid = episode_id.strip()
        return len(self._by_being_episode.get(being_id, {}).get(eid, set()))

    def remove_weakest_link_for_episode_by_being(
        self,
        being_id: BeingId,
        episode_id: str,
        *,
        now: datetime,
    ) -> bool:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        keys = list(self._by_being_episode.get(being_id, {}).get(episode_id.strip(), set()))
        if not keys:
            return False
        weakest_key = min(
            keys,
            key=lambda k: effective_link_strength(self._by_being_key[k], now),
        )
        link = self._by_being_key.pop(weakest_key, None)
        if link is None:
            return False
        # weakest_key のタプルから直接 episode_id を取り出す (= pop 済の link
        # フィールドに依存せずインデックス整合性を保つ。レビュー指摘反映)
        _, key_episode_a, key_episode_b, _ = weakest_key
        self._unregister_being_episode(being_id, key_episode_a, weakest_key)
        self._unregister_being_episode(being_id, key_episode_b, weakest_key)
        return True

    def list_all_links_for_being(self, being_id: BeingId) -> list[MemoryLink]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        return [
            ln
            for key, ln in self._by_being_key.items()
            if key[0] == being_id
        ]
