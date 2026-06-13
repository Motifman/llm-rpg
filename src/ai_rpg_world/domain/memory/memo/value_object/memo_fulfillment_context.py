"""MemoFulfillmentContext — memo_done 時の周辺コンテキスト snapshot。

DDD 再編 (Issue #470 Phase 1 PR3): 元 ``application/llm/contracts/dtos.py``
から domain に昇格。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Tuple


@dataclass(frozen=True)
class MemoFulfillmentContext:
    """``memo_done`` 呼び出し時の周辺コンテキスト snapshot。

    LLM が memo を完了マークした瞬間の sliding_window / action_result_store の
    抜粋を凍結保存する。後で episodic cue 経由で recall する際に「何があって
    達成したか」を辿る情報源となる (Issue #188 Phase 1a)。

    完了タイミングを LLM が逃すと snapshot が空になりがちなので、tool
    description で「達成したらすぐに memo_done」を促す。
    """

    completed_at: datetime
    completed_at_tick: Optional[int] = None
    recent_observation_proses: Tuple[str, ...] = ()
    recent_action_summaries: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.completed_at, datetime):
            raise TypeError("completed_at must be datetime")
        if self.completed_at_tick is not None and not isinstance(
            self.completed_at_tick, int
        ):
            raise TypeError("completed_at_tick must be int or None")
        if not isinstance(self.recent_observation_proses, tuple):
            raise TypeError("recent_observation_proses must be tuple")
        if not isinstance(self.recent_action_summaries, tuple):
            raise TypeError("recent_action_summaries must be tuple")


__all__ = ["MemoFulfillmentContext"]
