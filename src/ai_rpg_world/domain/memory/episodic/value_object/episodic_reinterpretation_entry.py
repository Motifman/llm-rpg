"""EpisodicReinterpretationEntry — 現在視点での episode 再解釈。

DDD 再編 (Issue #470 Phase 1 PR5): 元
``application/llm/contracts/episodic_reinterpretation.py`` から domain に昇格。

active entry だけが prompt 参照に使われる。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from ai_rpg_world.domain.memory.episodic.value_object._validators import (
    reject_blank,
    validate_str_tuple,
)
from ai_rpg_world.domain.memory.episodic.value_object.episodic_reinterpretation_status import (
    EpisodicReinterpretationStatus,
)


@dataclass(frozen=True)
class EpisodicReinterpretationEntry:
    """現在視点での episode 再解釈。active entry だけを prompt 参照に使う。"""

    entry_id: str
    player_id: int
    episode_id: str
    created_at: datetime
    turn_index: int
    current_interpretation: str
    current_recall_text: str
    source_recall_ids: tuple[str, ...]
    status: EpisodicReinterpretationStatus = EpisodicReinterpretationStatus.ACTIVE
    superseded_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry_id", reject_blank("entry_id", self.entry_id))
        if not isinstance(self.player_id, int):
            raise TypeError("player_id must be int")
        object.__setattr__(self, "episode_id", reject_blank("episode_id", self.episode_id))
        if not isinstance(self.created_at, datetime):
            raise TypeError("created_at must be datetime")
        if not isinstance(self.turn_index, int):
            raise TypeError("turn_index must be int")
        if self.turn_index < 0:
            raise ValueError("turn_index must be 0 or greater")
        object.__setattr__(
            self,
            "current_interpretation",
            reject_blank("current_interpretation", self.current_interpretation),
        )
        object.__setattr__(
            self,
            "current_recall_text",
            reject_blank("current_recall_text", self.current_recall_text),
        )
        object.__setattr__(
            self,
            "source_recall_ids",
            validate_str_tuple("source_recall_ids", self.source_recall_ids),
        )
        if not isinstance(self.status, EpisodicReinterpretationStatus):
            object.__setattr__(self, "status", EpisodicReinterpretationStatus(str(self.status)))
        if self.superseded_at is not None and not isinstance(self.superseded_at, datetime):
            raise TypeError("superseded_at must be datetime or None")
        if (
            self.status == EpisodicReinterpretationStatus.ACTIVE
            and self.superseded_at is not None
        ):
            raise ValueError("active entry must not have superseded_at")


__all__ = ["EpisodicReinterpretationEntry", "EpisodicReinterpretationStatus"]
