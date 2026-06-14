"""MemoryLinkRepository のインメモリ実装。

Phase 3 Step 3c-3 (Issue #470): legacy player_id 版を撤去し、being_id 版のみ
を残した。
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

BeingLinkKey = Tuple[BeingId, str, str, MemoryLinkType]


def _being_key_for_link(being_id: BeingId, link: MemoryLink) -> BeingLinkKey:
    # MemoryLink.__post_init__ で normalize_episode_pair 済 (= a < b) 前提
    return (being_id, link.episode_id_a, link.episode_id_b, link.link_type)


class InMemoryMemoryLinkStore(MemoryLinkRepository):
    def __init__(self) -> None:
        self._by_being_key: Dict[BeingLinkKey, MemoryLink] = {}
        self._by_being_episode: DefaultDict[
            BeingId, DefaultDict[str, Set[BeingLinkKey]]
        ] = defaultdict(lambda: defaultdict(set))

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
        # フィールドに依存せずインデックス整合性を保つ)
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

    def replace_all_by_being(
        self, being_id: BeingId, links: list[MemoryLink]
    ) -> None:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(links, list):
            raise TypeError("links must be list")
        for ln in links:
            if not isinstance(ln, MemoryLink):
                raise TypeError("links elements must be MemoryLink")
        # 当該 being の既存 entry / episode index を drop。
        for key in list(self._by_being_key.keys()):
            if key[0] == being_id:
                del self._by_being_key[key]
        if being_id in self._by_being_episode:
            del self._by_being_episode[being_id]
        # 改めて登録。
        for ln in links:
            key = _being_key_for_link(being_id, ln)
            self._by_being_key[key] = ln
            self._register_being_episode(being_id, ln.episode_id_a, key)
            self._register_being_episode(being_id, ln.episode_id_b, key)
