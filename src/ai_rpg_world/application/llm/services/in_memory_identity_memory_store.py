"""Identity Memory（自己像・長期信念）の in-memory 実装。長期事実ストアとは別経路。"""

from __future__ import annotations

from threading import RLock
from typing import Dict, List

from ai_rpg_world.application.llm.contracts.interfaces import IIdentityMemoryStore
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class InMemoryIdentityMemoryStore(IIdentityMemoryStore):
    """Consolidation や Memory Reflection の identity 候補の保存先（MVP）。"""

    def __init__(self, max_entries_per_player: int = 500) -> None:
        if max_entries_per_player <= 0:
            raise ValueError("max_entries_per_player must be greater than 0")
        self._max_entries = max_entries_per_player
        self._by_player: Dict[int, List[str]] = {}
        self._lock = RLock()

    def append_statement(
        self, player_id: PlayerId, text: str, *, source_note: str = ""
    ) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(text, str):
            raise TypeError("text must be str")
        if not isinstance(source_note, str):
            raise TypeError("source_note must be str")
        line = text.strip()
        if not line:
            raise ValueError("text must not be empty")
        if source_note.strip():
            line = f"{line} （{source_note.strip()}）"
        with self._lock:
            lst = self._by_player.setdefault(player_id.value, [])
            lst.append(line)
            overflow = len(lst) - self._max_entries
            if overflow > 0:
                del lst[:overflow]

    def list_statements(self, player_id: PlayerId, limit: int) -> tuple[str, ...]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if limit < 0:
            raise ValueError("limit must be 0 or greater")
        if limit == 0:
            return ()
        with self._lock:
            lst = self._by_player.get(player_id.value, [])
            slice_ = lst[-limit:]
            return tuple(slice_)
