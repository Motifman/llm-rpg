"""エピソード集約から昇格したセマンティック要約（長期記憶プロトタイプ）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Tuple


@dataclass(frozen=True)
class SemanticMemoryEntry:
    """クラスタ根拠付きの一般化テキスト。"""

    entry_id: str
    player_id: int
    text: str
    evidence_episode_ids: Tuple[str, ...]
    confidence: float
    created_at: datetime

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
        if not isinstance(self.confidence, (int, float)) or not (0.0 <= float(self.confidence) <= 1.0):
            raise ValueError("confidence must be float in [0,1]")
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be datetime")
