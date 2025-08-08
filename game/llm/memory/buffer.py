from __future__ import annotations

from collections import deque
from typing import Deque, Iterable, List, Optional

from game.llm.memory.schemas import MessageBase, total_tokens


class FixedLengthMessageBuffer:
    """プレイヤー単位の固定長リングバッファ。

    - maxlen: メッセージ件数の上限
    - append: 末尾に追加。超過時は先頭から自動で追い出し
    - get_recent: 直近から limit 件を取得
    - get_for_token_budget: トークン予算に収まるまで遡って収集（直近優先）
    """

    def __init__(self, maxlen: int = 20) -> None:
        self._maxlen: int = maxlen
        self._buffer: Deque[MessageBase] = deque(maxlen=maxlen)

    @property
    def maxlen(self) -> int:
        return self._maxlen

    def append(self, message: MessageBase) -> None:
        message.ensure_estimates()
        self._buffer.append(message)

    def extend(self, messages: Iterable[MessageBase]) -> None:
        for m in messages:
            self.append(m)

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self._buffer)

    def get_all(self) -> List[MessageBase]:
        return list(self._buffer)

    def get_recent(self, limit: Optional[int] = None) -> List[MessageBase]:
        if limit is None or limit >= len(self._buffer):
            return list(self._buffer)
        # 直近優先で limit 件
        return list(self._buffer)[-limit:]

    def get_for_token_budget(self, token_budget: int) -> List[MessageBase]:
        """直近から遡って、合計トークンが予算内に収まるメッセージ列を返す。"""
        if token_budget <= 0:
            return []
        collected: List[MessageBase] = []
        running_total = 0
        for msg in reversed(self._buffer):
            msg.ensure_estimates()
            next_total = running_total + msg.tokens_estimate
            if next_total > token_budget:
                break
            collected.append(msg)
            running_total = next_total
        collected.reverse()
        return collected


