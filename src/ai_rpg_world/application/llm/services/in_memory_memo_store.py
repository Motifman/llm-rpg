"""Memo ストアの in-memory 実装。

Issue #188 Phase 1a で ``InMemoryTodoStore`` から改名・拡張。
- ``MemoEntry`` に ``added_at_tick`` / ``completed_at`` / ``fulfillment_context``
  を追加し、完了時の周辺 context を snapshot できるようにした
- 旧 ``InMemoryTodoStore`` は本クラスのエイリアスとして残す (後方互換)

Phase 3 Step 3a-1 (Issue #470): being_id 版 API を並走追加。
内部 store は player_id 版と完全独立 (= 同一 caller が新旧 API を混在させない
前提)。Step 3a-2 で caller を新 API に切替え、3a-3 で player_id 版を撤去する。
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional

from ai_rpg_world.domain.being.value_object.being_id import BeingId
from ai_rpg_world.domain.memory.memo.value_object.memo_entry import MemoEntry
from ai_rpg_world.domain.memory.memo.value_object.memo_fulfillment_context import MemoFulfillmentContext
from ai_rpg_world.domain.memory.memo.repository.memo_repository import MemoRepository
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class InMemoryMemoStore(MemoRepository):
    """プレイヤーごとに memo をリストで保持する in-memory 実装。

    内部に 2 つの独立した store を持つ:
    - ``_store`` / ``_id_to_index``: player_id 版 (= 旧 API、Step 3a-3 で撤去予定)
    - ``_being_store`` / ``_being_id_to_index``: being_id 版 (= 新 API)
    """

    def __init__(self) -> None:
        self._store: Dict[int, List[MemoEntry]] = {}
        self._id_to_index: Dict[int, Dict[str, int]] = {}
        # being_id 版の並走 store (Phase 3 Step 3a-1 で追加)
        self._being_store: Dict[BeingId, List[MemoEntry]] = {}
        self._being_id_to_index: Dict[BeingId, Dict[str, int]] = {}

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


    # ===== Phase 3 Step 3a-1: being_id 版を並走追加 =====
    # 既存 player_id 版の実装ロジックを being_id keyed に焼き直したもの。
    # 同一 store ファイル内で並走し、Step 3a-2 で caller 移行 → 3a-3 で player_id
    # 版を撤去する。

    def add_by_being(
        self,
        being_id: BeingId,
        content: str,
        *,
        current_tick: int | None = None,
    ) -> str:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
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
        if being_id not in self._being_store:
            self._being_store[being_id] = []
            self._being_id_to_index[being_id] = {}
        idx = len(self._being_store[being_id])
        self._being_store[being_id].append(entry)
        self._being_id_to_index[being_id][memo_id] = idx
        return memo_id

    def list_uncompleted_by_being(self, being_id: BeingId) -> List[MemoEntry]:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        entries = self._being_store.get(being_id, [])
        uncompleted = [e for e in entries if not e.completed]
        return sorted(uncompleted, key=lambda e: e.added_at, reverse=True)

    def complete_by_being(
        self,
        being_id: BeingId,
        memo_id: str,
        *,
        fulfillment_context: MemoFulfillmentContext | None = None,
    ) -> bool:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(memo_id, str):
            raise TypeError("memo_id must be str")
        if fulfillment_context is not None and not isinstance(
            fulfillment_context, MemoFulfillmentContext
        ):
            raise TypeError(
                "fulfillment_context must be MemoFulfillmentContext or None"
            )
        if being_id not in self._being_store:
            return False
        idx = self._being_id_to_index.get(being_id, {}).get(memo_id)
        if idx is None:
            return False
        entry = self._being_store[being_id][idx]
        # 既に完了済みなら冪等に True を返す (= 完了タイムスタンプを上書きしない)。
        # 旧 player_id 版 complete() と挙動を揃える。
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
        self._being_store[being_id][idx] = new_entry
        return True

    def remove_by_being(self, being_id: BeingId, memo_id: str) -> bool:
        if not isinstance(being_id, BeingId):
            raise TypeError("being_id must be BeingId")
        if not isinstance(memo_id, str):
            raise TypeError("memo_id must be str")
        if being_id not in self._being_store:
            return False
        idx = self._being_id_to_index.get(being_id, {}).get(memo_id)
        if idx is None:
            return False
        self._being_store[being_id].pop(idx)
        del self._being_id_to_index[being_id][memo_id]
        for tid, i in list(self._being_id_to_index[being_id].items()):
            if i > idx:
                self._being_id_to_index[being_id][tid] = i - 1
        return True


# 後方互換: 旧名 ``InMemoryTodoStore`` は本クラスのエイリアス。
# 新規コードは InMemoryMemoStore を使うこと。
InMemoryTodoStore = InMemoryMemoStore
