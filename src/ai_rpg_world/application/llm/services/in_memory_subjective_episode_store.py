"""SubjectiveEpisode（v2）の in-memory 実装。"""

from dataclasses import replace
from datetime import datetime
from threading import RLock
from typing import Dict, List

from ai_rpg_world.application.llm.contracts.dtos import SubjectiveEpisode
from ai_rpg_world.application.llm.contracts.interfaces import ISubjectiveEpisodeStore
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class InMemorySubjectiveEpisodeStore(ISubjectiveEpisodeStore):
    """プレイヤーごとに主観エピソードを保持する。"""

    def __init__(self, max_entries_per_player: int = 2000) -> None:
        if max_entries_per_player <= 0:
            raise ValueError("max_entries_per_player must be greater than 0")
        self._max_entries = max_entries_per_player
        self._by_player: Dict[int, List[SubjectiveEpisode]] = {}
        self._index: Dict[int, Dict[str, SubjectiveEpisode]] = {}
        self._lock = RLock()

    def _key(self, player_id: PlayerId) -> int:
        return player_id.value

    def put(self, player_id: PlayerId, episode: SubjectiveEpisode) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(episode, SubjectiveEpisode):
            raise TypeError("episode must be SubjectiveEpisode")
        if episode.agent_id != player_id.value:
            raise ValueError("episode.agent_id must match player_id")
        with self._lock:
            key = self._key(player_id)
            if key not in self._by_player:
                self._by_player[key] = []
                self._index[key] = {}
            self._index[key][episode.episode_id] = episode
            lst = self._by_player[key]
            lst[:] = [e for e in lst if e.episode_id != episode.episode_id]
            lst.append(episode)
            if len(lst) > self._max_entries:
                removed = lst[:-self._max_entries]
                self._by_player[key] = lst[-self._max_entries :]
                for old in removed:
                    self._index[key].pop(old.episode_id, None)

    def get_by_episode_id(
        self, player_id: PlayerId, episode_id: str
    ) -> SubjectiveEpisode | None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(episode_id, str):
            raise TypeError("episode_id must be str")
        with self._lock:
            return self._index.get(self._key(player_id), {}).get(episode_id)

    def list_recent(self, player_id: PlayerId, limit: int) -> List[SubjectiveEpisode]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if limit < 0:
            raise ValueError("limit must be 0 or greater")
        if limit == 0:
            return []
        with self._lock:
            key = self._key(player_id)
            entries = self._by_player.get(key, [])
            sorted_entries = sorted(entries, key=lambda e: e.created_at, reverse=True)
            return sorted_entries[:limit]

    def list_all_episodes(self, player_id: PlayerId) -> List[SubjectiveEpisode]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        with self._lock:
            key = self._key(player_id)
            entries = list(self._by_player.get(key, []))
        entries.sort(key=lambda e: (e.created_at, e.episode_id))
        return entries

    def record_passive_recall(self, player_id: PlayerId, episode_id: str) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(episode_id, str):
            raise TypeError("episode_id must be str")
        with self._lock:
            ep = self._index.get(self._key(player_id), {}).get(episode_id)
        if ep is None:
            return
        updated = replace(
            ep,
            recall_count=ep.recall_count + 1,
            last_recalled_at=datetime.now(),
        )
        self.put(player_id, updated)

    def count_reflection_journal_entries(self, player_id: PlayerId) -> int:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        with self._lock:
            total = 0
            for ep in self._by_player.get(self._key(player_id), []):
                total += len(ep.memory_reflection_journal)
            return total
