"""作業メモストアの in-memory 実装"""

from typing import Dict, List

from ai_rpg_world.application.llm.contracts.interfaces import IWorkingMemoryStore
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class InMemoryWorkingMemoryStore(IWorkingMemoryStore):
    """プレイヤーごとに作業メモをリストで保持する in-memory 実装。
    直近 max_entries 件を保持し、超過分は古い順に削除する。
    """

    def __init__(self, max_entries_per_player: int = 50) -> None:
        if max_entries_per_player <= 0:
            raise ValueError("max_entries_per_player must be greater than 0")
        self._max_entries = max_entries_per_player
        self._store: Dict[int, List[str]] = {}

    def _key(self, player_id: PlayerId) -> int:
        return player_id.value

    def append(self, player_id: PlayerId, text: str) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(text, str):
            raise TypeError("text must be str")
        key = self._key(player_id)
        if key not in self._store:
            self._store[key] = []
        self._store[key].append(text)
        if len(self._store[key]) > self._max_entries:
            self._store[key] = self._store[key][-self._max_entries :]

    def get_recent(self, player_id: PlayerId, limit: int) -> List[str]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if limit < 0:
            raise ValueError("limit must be 0 or greater")
        if limit == 0:
            return []
        key = self._key(player_id)
        entries = self._store.get(key, [])
        return entries[-limit:][::-1]

    def clear(self, player_id: PlayerId) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        key = self._key(player_id)
        if key in self._store:
            self._store[key] = []
