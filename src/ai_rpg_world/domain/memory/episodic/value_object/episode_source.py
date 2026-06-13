"""EpisodeSource — エピソードの材料となった event_ids 集合。

DDD 再編 (Issue #470 Phase 1 PR2): 元 ``application/llm/contracts/episodic_memory.py``
から domain に昇格。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class EpisodeSource:
    """エピソードの材料となったイベント ID の参照集合。

    不変フィールドとして扱い、後続処理で書き換えないことを前提とする。
    MVP では追跡可能性のため event_ids は最低 1 件必須。
    """

    event_ids: Tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.event_ids, tuple):
            raise TypeError("event_ids must be a tuple[str, ...]")
        if len(self.event_ids) == 0:
            raise ValueError("event_ids must contain at least one id")
        normalized: list[str] = []
        for idx, raw in enumerate(self.event_ids):
            if not isinstance(raw, str):
                raise TypeError(f"event_ids[{idx}] must be str")
            rid = raw.strip()
            if not rid:
                raise ValueError(f"event_ids[{idx}] must not be empty or whitespace-only")
            normalized.append(rid)
        object.__setattr__(self, "event_ids", tuple(normalized))


__all__ = ["EpisodeSource"]
