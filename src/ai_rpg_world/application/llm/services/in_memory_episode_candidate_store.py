"""EpisodeCandidate の in-memory 実装。"""

from typing import Dict, List, Set

from ai_rpg_world.application.llm.contracts.dtos import EpisodeCandidate
from ai_rpg_world.application.llm.contracts.interfaces import IEpisodeCandidateStore
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class InMemoryEpisodeCandidateStore(IEpisodeCandidateStore):
    """プレイヤーごとに episode candidate を保持する in-memory store。"""

    def __init__(self, max_entries_per_player: int = 1000) -> None:
        if max_entries_per_player <= 0:
            raise ValueError("max_entries_per_player must be greater than 0")
        self._max_entries = max_entries_per_player
        self._store: Dict[int, List[EpisodeCandidate]] = {}
        self._source_index: Dict[int, Set[str]] = {}

    def _key(self, player_id: PlayerId) -> int:
        return player_id.value

    def add(self, player_id: PlayerId, candidate: EpisodeCandidate) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(candidate, EpisodeCandidate):
            raise TypeError("candidate must be EpisodeCandidate")
        if candidate.agent_id != player_id.value:
            raise ValueError("candidate.agent_id must match player_id")
        key = self._key(player_id)
        if key not in self._store:
            self._store[key] = []
            self._source_index[key] = set()
        self._store[key].append(candidate)
        self._source_index[key].update(candidate.source_trace_ids)
        if len(self._store[key]) > self._max_entries:
            removed = self._store[key][:-self._max_entries]
            self._store[key] = self._store[key][-self._max_entries :]
            for old in removed:
                for source_id in old.source_trace_ids:
                    if not any(source_id in c.source_trace_ids for c in self._store[key]):
                        self._source_index[key].discard(source_id)

    def get_recent(self, player_id: PlayerId, limit: int) -> List[EpisodeCandidate]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if limit < 0:
            raise ValueError("limit must be 0 or greater")
        if limit == 0:
            return []
        key = self._key(player_id)
        entries = self._store.get(key, [])
        sorted_entries = sorted(entries, key=lambda e: e.created_at, reverse=True)
        return sorted_entries[:limit]

    def contains_source_trace(self, player_id: PlayerId, source_trace_id: str) -> bool:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(source_trace_id, str):
            raise TypeError("source_trace_id must be str")
        key = self._key(player_id)
        return source_trace_id in self._source_index.get(key, set())
