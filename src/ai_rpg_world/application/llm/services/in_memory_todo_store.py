"""TODO ストアの in-memory 実装"""

import uuid
from datetime import datetime
from typing import Dict, List

from ai_rpg_world.application.llm.contracts.dtos import TodoEntry
from ai_rpg_world.application.llm.contracts.interfaces import ITodoStore
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class InMemoryTodoStore(ITodoStore):
    """プレイヤーごとに TODO をリストで保持する in-memory 実装。"""

    def __init__(self) -> None:
        self._store: Dict[int, List[TodoEntry]] = {}
        self._id_to_index: Dict[int, Dict[str, int]] = {}

    def _key(self, player_id: PlayerId) -> int:
        return player_id.value

    def add(self, player_id: PlayerId, content: str) -> str:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(content, str):
            raise TypeError("content must be str")
        todo_id = str(uuid.uuid4())
        entry = TodoEntry(
            id=todo_id,
            content=content,
            added_at=datetime.now(),
            completed=False,
        )
        key = self._key(player_id)
        if key not in self._store:
            self._store[key] = []
            self._id_to_index[key] = {}
        idx = len(self._store[key])
        self._store[key].append(entry)
        self._id_to_index[key][todo_id] = idx
        return todo_id

    def list_uncompleted(self, player_id: PlayerId) -> List[TodoEntry]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        key = self._key(player_id)
        entries = self._store.get(key, [])
        uncompleted = [e for e in entries if not e.completed]
        return sorted(uncompleted, key=lambda e: e.added_at, reverse=True)

    def complete(self, player_id: PlayerId, todo_id: str) -> bool:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(todo_id, str):
            raise TypeError("todo_id must be str")
        key = self._key(player_id)
        if key not in self._store:
            return False
        idx = self._id_to_index.get(key, {}).get(todo_id)
        if idx is None:
            return False
        entry = self._store[key][idx]
        if entry.completed:
            return True
        new_entry = TodoEntry(
            id=entry.id,
            content=entry.content,
            added_at=entry.added_at,
            completed=True,
        )
        self._store[key][idx] = new_entry
        return True

    def remove(self, player_id: PlayerId, todo_id: str) -> bool:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(todo_id, str):
            raise TypeError("todo_id must be str")
        key = self._key(player_id)
        if key not in self._store:
            return False
        idx = self._id_to_index.get(key, {}).get(todo_id)
        if idx is None:
            return False
        self._store[key].pop(idx)
        del self._id_to_index[key][todo_id]
        for tid, i in list(self._id_to_index[key].items()):
            if i > idx:
                self._id_to_index[key][tid] = i - 1
        return True
