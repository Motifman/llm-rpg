"""Memo ストアの in-memory 実装。

Issue #188 Phase 1a で ``InMemoryTodoStore`` から改名・拡張。
- ``MemoEntry`` に ``added_at_tick`` / ``completed_at`` / ``fulfillment_context``
  を追加し、完了時の周辺 context を snapshot できるようにした
- 旧 ``InMemoryTodoStore`` は本クラスのエイリアスとして残す (後方互換)
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from ai_rpg_world.domain.memory.memo.value_object.memo_entry import MemoEntry
from ai_rpg_world.domain.memory.memo.value_object.memo_fulfillment_context import MemoFulfillmentContext
from ai_rpg_world.domain.memory.memo.repository.memo_repository import MemoRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class InMemoryMemoStore(MemoRepository):
    """プレイヤーごとに memo をリストで保持する in-memory 実装。"""

    def __init__(self) -> None:
        self._store: Dict[int, List[MemoEntry]] = {}
        self._id_to_index: Dict[int, Dict[str, int]] = {}

    def _key(self, player_id: PlayerId) -> int:
        return player_id.value

    def add(
        self,
        player_id: PlayerId,
        content: str,
        *,
        current_tick: Optional[int] = None,
    ) -> str:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(content, str):
            raise TypeError("content must be str")
        if current_tick is not None and not isinstance(current_tick, int):
            raise TypeError("current_tick must be int or None")
        memo_id = str(uuid.uuid4())
        entry = MemoEntry(
            id=memo_id,
            content=content,
            added_at=datetime.now(),
            completed=False,
            added_at_tick=current_tick,
        )
        key = self._key(player_id)
        if key not in self._store:
            self._store[key] = []
            self._id_to_index[key] = {}
        idx = len(self._store[key])
        self._store[key].append(entry)
        self._id_to_index[key][memo_id] = idx
        return memo_id

    def list_uncompleted(self, player_id: PlayerId) -> List[MemoEntry]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        key = self._key(player_id)
        entries = self._store.get(key, [])
        uncompleted = [e for e in entries if not e.completed]
        return sorted(uncompleted, key=lambda e: e.added_at, reverse=True)

    def complete(
        self,
        player_id: PlayerId,
        memo_id: str,
        *,
        fulfillment_context: Optional[MemoFulfillmentContext] = None,
    ) -> bool:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(memo_id, str):
            raise TypeError("memo_id must be str")
        if fulfillment_context is not None and not isinstance(
            fulfillment_context, MemoFulfillmentContext
        ):
            raise TypeError(
                "fulfillment_context must be MemoFulfillmentContext or None"
            )
        key = self._key(player_id)
        if key not in self._store:
            return False
        idx = self._id_to_index.get(key, {}).get(memo_id)
        if idx is None:
            return False
        entry = self._store[key][idx]
        if entry.completed:
            return True
        new_entry = MemoEntry(
            id=entry.id,
            content=entry.content,
            added_at=entry.added_at,
            completed=True,
            added_at_tick=entry.added_at_tick,
            completed_at=datetime.now(),
            fulfillment_context=fulfillment_context,
        )
        self._store[key][idx] = new_entry
        return True

    def remove(self, player_id: PlayerId, memo_id: str) -> bool:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(memo_id, str):
            raise TypeError("memo_id must be str")
        key = self._key(player_id)
        if key not in self._store:
            return False
        idx = self._id_to_index.get(key, {}).get(memo_id)
        if idx is None:
            return False
        self._store[key].pop(idx)
        del self._id_to_index[key][memo_id]
        for tid, i in list(self._id_to_index[key].items()):
            if i > idx:
                self._id_to_index[key][tid] = i - 1
        return True


# 後方互換: 旧名 ``InMemoryTodoStore`` は本クラスのエイリアス。
# 新規コードは InMemoryMemoStore を使うこと。
InMemoryTodoStore = InMemoryMemoStore
