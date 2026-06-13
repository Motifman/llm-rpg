"""L4 中期帯 (mid summary) の Value Object。

DDD 再編 (Issue #470 Phase 1): 元 ``application/llm/contracts/short_term_memory.py``
から domain に昇格した純粋 Value Object。

不変条件はすべて ``__post_init__`` で検証する (frozen + validation)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Tuple


@dataclass(frozen=True)
class L4MidSummary:
    """中期帯 (L4) 1 世代分の主観要約。

    Phase 2 (#356 後続): sliding window が 15 raw 件を超えたタイミングで
    LLM で生成される。3 世代まで保持して prompt §「【最近の流れ】」に出す。

    schema 設計指針 (docs §4.1):
    - **学び / 関係性 / 世界ルール は含めない** (semantic 経路の責務)
    - **narrative continuity** に絞る (流れ + 気分 + 未解決)
    - **永続名のみ** (P1 等のターン局所ラベルを焼かない)
    """

    summary_id: str
    player_id: int
    raw_count: int
    generated_at: datetime
    compressed_activity: str
    emotional_summary: str
    unresolved: Tuple[str, ...] = ()
    # template fallback で生成された (= LLM 抽象化が走らなかった) かを表すフラグ。
    # trace / 分析で「LLM 成功率」を出すのに使う。default False。
    is_fallback: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.summary_id, str) or not self.summary_id.strip():
            raise ValueError("summary_id must be non-empty str")
        if not isinstance(self.player_id, int):
            raise TypeError("player_id must be int")
        if not isinstance(self.raw_count, int) or self.raw_count < 0:
            raise ValueError("raw_count must be non-negative int")
        if not isinstance(self.generated_at, datetime):
            raise TypeError("generated_at must be datetime")
        if not isinstance(self.compressed_activity, str):
            raise TypeError("compressed_activity must be str")
        if not isinstance(self.emotional_summary, str):
            raise TypeError("emotional_summary must be str")
        if not isinstance(self.unresolved, tuple):
            raise TypeError("unresolved must be tuple[str, ...]")
        for i, item in enumerate(self.unresolved):
            if not isinstance(item, str):
                raise TypeError(f"unresolved[{i}] must be str")
        if not isinstance(self.is_fallback, bool):
            raise TypeError("is_fallback must be bool")


__all__ = ["L4MidSummary"]
