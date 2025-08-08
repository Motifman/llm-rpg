from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from game.llm.memory.buffer import FixedLengthMessageBuffer
from game.llm.memory.schemas import MessageBase


class PlayerMemoryStore:
    """プレイヤーごとのメモリバッファを管理するストア。

    初期実装はインメモリ。将来的に永続化クラスへ差し替え可能なAPIにする。
    """

    def __init__(self, default_maxlen: int = 20) -> None:
        self._default_maxlen = default_maxlen
        self._player_id_to_buffer: Dict[str, FixedLengthMessageBuffer] = {}

    def _get_or_create(self, player_id: str) -> FixedLengthMessageBuffer:
        if player_id not in self._player_id_to_buffer:
            self._player_id_to_buffer[player_id] = FixedLengthMessageBuffer(maxlen=self._default_maxlen)
        return self._player_id_to_buffer[player_id]

    def append(self, player_id: str, message: MessageBase) -> None:
        self._get_or_create(player_id).append(message)

    def extend(self, player_id: str, messages: Iterable[MessageBase]) -> None:
        self._get_or_create(player_id).extend(messages)

    def get_recent(self, player_id: str, limit: Optional[int] = None) -> List[MessageBase]:
        return self._get_or_create(player_id).get_recent(limit)

    def get_for_token_budget(self, player_id: str, token_budget: int) -> List[MessageBase]:
        return self._get_or_create(player_id).get_for_token_budget(token_budget)

    def get_all(self, player_id: str) -> List[MessageBase]:
        return self._get_or_create(player_id).get_all()


