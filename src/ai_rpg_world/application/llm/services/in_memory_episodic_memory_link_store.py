"""IMemoryLinkStore のインメモリ実装。"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import DefaultDict, Dict, Set, Tuple

from ai_rpg_world.application.llm.contracts.episodic_memory_link import (
    MemoryLink,
    MemoryLinkType,
    effective_link_strength,
    normalize_episode_pair,
)
from ai_rpg_world.application.llm.contracts.episodic_memory_link_store_port import (
    IMemoryLinkStore,
)

LinkKey = Tuple[int, str, str, MemoryLinkType]


def _key_for_link(link: MemoryLink) -> LinkKey:
    return (link.player_id, link.episode_id_a, link.episode_id_b, link.link_type)


class InMemoryMemoryLinkStore(IMemoryLinkStore):
    def __init__(self) -> None:
        self._by_key: Dict[LinkKey, MemoryLink] = {}
        self._by_episode: DefaultDict[int, DefaultDict[str, Set[LinkKey]]] = defaultdict(
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
