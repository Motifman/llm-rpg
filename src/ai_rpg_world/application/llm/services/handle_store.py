"""memory_query output_mode=handle 用のサーバ内参照ストア。1 turn 限定。"""

import uuid
from typing import Any, Dict, List, Optional

from ai_rpg_world.application.llm.contracts.interfaces import IHandleStore
from ai_rpg_world.domain.player.value_object.player_id import PlayerId


class InMemoryHandleStore(IHandleStore):
    """プレイヤー別に handle を保持するインメモリ実装。"""

    def __init__(self) -> None:
        self._store: Dict[int, Dict[str, Dict[str, Any]]] = {}

    def put(
        self,
        player_id: PlayerId,
        handle_id: str,
        data: List[Dict[str, Any]],
        expr: str,
    ) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        if not isinstance(handle_id, str) or not handle_id:
            raise TypeError("handle_id must be non-empty str")
        if not isinstance(data, list):
            raise TypeError("data must be list")
        if not isinstance(expr, str):
            raise TypeError("expr must be str")
        pid = player_id.value
        if pid not in self._store:
            self._store[pid] = {}
        self._store[pid][handle_id] = {"data": data, "expr": expr}

    def get(
        self, player_id: PlayerId, handle_id: str
    ) -> Optional[List[Dict[str, Any]]]:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        pid = player_id.value
        if pid not in self._store:
            return None
        entry = self._store[pid].get(handle_id)
        if entry is None:
            return None
        return entry["data"]

    def clear_player(self, player_id: PlayerId) -> None:
        if not isinstance(player_id, PlayerId):
            raise TypeError("player_id must be PlayerId")
        self._store.pop(player_id.value, None)


def generate_handle_id() -> str:
    """一意の handle_id を生成する。"""
    return "h_" + uuid.uuid4().hex[:12]
