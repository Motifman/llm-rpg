"""Intent ID の単純カウンタ実装。

実用上は「1 つの IntentQueue インスタンスの生存期間で一意な int」が出れば
十分。プロセス再起動で 0 から振り直されても、queue 自体が in-memory な集約
として揮発するため不整合は生じない。
"""

from __future__ import annotations

import threading

from ai_rpg_world.domain.intent.value_object.intent_id import IntentId


class IntentIdGenerator:
    """単調増加 int を返すスレッドセーフなカウンタ。

    threading.Lock で囲っているのは、`tool_executor` を将来 `run_in_executor`
    で別スレッドにオフロードする可能性に備えた防御策。現状は asyncio 単一
    スレッドなので競合は起きないが、コストはほぼゼロ。
    """

    def __init__(self, start: int = 1) -> None:
        if start < 0:
            raise ValueError("start must be >= 0")
        self._next = start
        self._lock = threading.Lock()

    def next_id(self) -> IntentId:
        with self._lock:
            value = self._next
            self._next += 1
        return IntentId(value)
