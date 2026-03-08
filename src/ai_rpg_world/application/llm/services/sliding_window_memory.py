"""スライディングウィンドウ記憶のデフォルト実装（in-memory）"""

from typing import Dict, List

from ai_rpg_world.application.observation.contracts.dtos import ObservationEntry
from ai_rpg_world.application.llm.contracts.interfaces import ISlidingWindowMemory
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class DefaultSlidingWindowMemory(ISlidingWindowMemory):
    """プレイヤーごとに観測をリストで保持し、直近 N 件を返す in-memory 実装。"""

    def __init__(self, max_entries_per_player: int = 100) -> None:
        if max_entries_per_player <= 0:
            raise ValueError("max_entries_per_player must be greater than 0")
        self._max_entries = max_entries_per_player
        self._store: Dict[int, List[ObservationEntry]] = {}

    def _key(self, player_id: PlayerId) -> int:
        return player_id.value

    def append(self, player_id: PlayerId, entry: ObservationEntry) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(entry, ObservationEntry):
            raise TypeError("entry must be ObservationEntry")
        key = self._key(player_id)
        if key not in self._store:
            self._store[key] = []
        self._store[key].append(entry)
        # スライディング: 古いものを捨てる
        if len(self._store[key]) > self._max_entries:
            self._store[key] = self._store[key][-self._max_entries :]

    def append_all(
        self, player_id: PlayerId, entries: List[ObservationEntry]
    ) -> List[ObservationEntry]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(entries, list):
            raise TypeError("entries must be list")
        for e in entries:
            if not isinstance(e, ObservationEntry):
                raise TypeError("entries must contain only ObservationEntry")
        key = self._key(player_id)
        if key not in self._store:
            self._store[key] = []
        self._store[key].extend(entries)
        overflow: List[ObservationEntry] = []
        if len(self._store[key]) > self._max_entries:
            n_overflow = len(self._store[key]) - self._max_entries
            overflow = self._store[key][:n_overflow]
            self._store[key] = self._store[key][-self._max_entries :]
        return overflow

    def get_recent(self, player_id: PlayerId, limit: int) -> List[ObservationEntry]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if limit < 0:
            raise ValueError("limit must be 0 or greater")
        key = self._key(player_id)
        entries = self._store.get(key, [])
        # 新しい順（occurred_at 降順）で返す。同一時刻は append 順を維持
        sorted_entries = sorted(entries, key=lambda e: e.occurred_at, reverse=True)
        return sorted_entries[:limit]
