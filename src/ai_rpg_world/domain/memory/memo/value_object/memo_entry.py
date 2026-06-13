"""MemoEntry — LLM が context に固定したい情報の 1 件。

DDD 再編 (Issue #470 Phase 1 PR3): 元 ``application/llm/contracts/dtos.py``
から domain に昇格。

K run (PR #466) で memo は LLM agent の **Plan tier 相当** の役割を担うこと
が観測された (memo_add + memo_done + memo_list で全 action の 34% を占めた)。
本 VO はその記憶単位。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from ai_rpg_world.domain.memory.memo.value_object.memo_fulfillment_context import (
    MemoFulfillmentContext,
)


@dataclass(frozen=True)
class MemoEntry:
    """LLM が context に固定したい情報の 1 件。

    Issue #188 Phase 1a で TodoEntry から改名・拡張。
    「TODO」というより **LLM が意図的にプロンプトに置いておきたい memo** で、
    抽象的な目標 / 戦略メモ / 注意事項 / 観察メモなど自由な内容を含められる。

    フィールド:
    - ``id``: 一意 ID (UUID)。memo_done で参照
    - ``content``: 自由文字列。tool 呼び出し時に LLM が指定
    - ``added_at``: 追加 datetime
    - ``added_at_tick``: 追加時の game tick (age 表示用)
    - ``completed``: LLM が memo_done を呼んだら True
    - ``completed_at`` / ``fulfillment_context``: 完了時の周辺 context snapshot
    """

    id: str
    content: str
    added_at: datetime
    completed: bool = False
    added_at_tick: Optional[int] = None
    completed_at: Optional[datetime] = None
    fulfillment_context: Optional[MemoFulfillmentContext] = None

    def __post_init__(self) -> None:
        if not isinstance(self.id, str):
            raise TypeError("id must be str")
        if not isinstance(self.content, str):
            raise TypeError("content must be str")
        if not isinstance(self.added_at, datetime):
            raise TypeError("added_at must be datetime")
        if not isinstance(self.completed, bool):
            raise TypeError("completed must be bool")
        if self.added_at_tick is not None and not isinstance(self.added_at_tick, int):
            raise TypeError("added_at_tick must be int or None")
        if self.completed_at is not None and not isinstance(self.completed_at, datetime):
            raise TypeError("completed_at must be datetime or None")
        if self.fulfillment_context is not None and not isinstance(
            self.fulfillment_context, MemoFulfillmentContext
        ):
            raise TypeError(
                "fulfillment_context must be MemoFulfillmentContext or None"
            )


# 後方互換: 旧 TodoEntry 名は MemoEntry の alias として残す (Issue #188 リネーム)。
# 新規コードは MemoEntry を使うこと。
TodoEntry = MemoEntry


__all__ = ["MemoEntry", "TodoEntry"]
