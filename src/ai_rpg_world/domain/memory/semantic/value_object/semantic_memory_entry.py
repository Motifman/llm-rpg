"""SemanticMemoryEntry — エピソード集約から昇格したセマンティック要約 (長期記憶プロトタイプ)。

DDD 再編 (Issue #470 Phase 1 PR3): 元
``application/llm/contracts/semantic_memory_entry.py`` から domain に昇格。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Tuple


@dataclass(frozen=True)
class SemanticMemoryEntry:
    """クラスタ根拠付きの一般化テキスト。

    Phase 1b で ``importance_score`` / ``tags`` を追加 (default で後方互換)。
    現状 (Phase 1b) は LLM 生成の場合だけ意味のある値が入り、決定論 gist の
    場合は default のまま。Phase 1c の passive top-K スコアリングで使う。
    """

    entry_id: str
    player_id: int
    text: str
    evidence_episode_ids: Tuple[str, ...]
    confidence: float
    created_at: datetime
    # Phase 1b 拡張: LLM gist の場合に値が入る。決定論 gist の場合は default
    # (importance_score=5, tags=()) のまま。Phase 1c で top-K スコアの
    # importance 項として使う予定。
    importance_score: int = 5
    tags: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.entry_id, str) or not self.entry_id.strip():
            raise ValueError("entry_id must be non-empty str")
        if not isinstance(self.player_id, int):
            raise TypeError("player_id must be int")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("text must be non-empty str")
        if not isinstance(self.evidence_episode_ids, tuple):
            raise TypeError("evidence_episode_ids must be tuple[str, ...]")
        for i, eid in enumerate(self.evidence_episode_ids):
            if not isinstance(eid, str) or not eid.strip():
                raise ValueError(f"evidence_episode_ids[{i}] must be non-empty str")
        if not isinstance(self.confidence, (int, float)) or not (
            0.0 <= float(self.confidence) <= 1.0
        ):
            raise ValueError("confidence must be float in [0,1]")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be datetime")
        if not isinstance(self.importance_score, int):
            raise TypeError("importance_score must be int")
        if not (1 <= self.importance_score <= 10):
            raise ValueError("importance_score must be in [1, 10]")
        if not isinstance(self.tags, tuple):
            raise TypeError("tags must be tuple[str, ...]")
        for i, tag in enumerate(self.tags):
            if not isinstance(tag, str) or not tag.strip():
                raise ValueError(f"tags[{i}] must be non-empty str")


__all__ = ["SemanticMemoryEntry"]
