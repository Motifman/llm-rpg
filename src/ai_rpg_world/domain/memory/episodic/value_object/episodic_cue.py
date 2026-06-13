"""EpisodicCue — 型付き想起手がかり。

DDD 再編 (Issue #470 Phase 1 PR2): 元 ``application/llm/contracts/episodic_memory.py``
から domain に昇格。
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.memory.episodic.value_object._validators import reject_blank
from ai_rpg_world.domain.memory.episodic.value_object.episodic_cue_source import (
    EpisodicCueSource,
)


@dataclass(frozen=True)
class EpisodicCue:
    """型付き想起手がかり。canonical は索引・マッチ用の安定キー（axis:value）。"""

    axis: str
    value: str
    source: EpisodicCueSource

    def __post_init__(self) -> None:
        if not isinstance(self.source, EpisodicCueSource):
            raise TypeError("source must be EpisodicCueSource")
        axis_stripped = reject_blank("axis", self.axis)
        value_stripped = reject_blank("value", self.value)
        if ":" in axis_stripped:
            raise ValueError("axis must not contain ':'")
        object.__setattr__(self, "axis", axis_stripped.lower())
        object.__setattr__(self, "value", value_stripped)

    def to_canonical(self) -> str:
        return f"{self.axis}:{self.value}"


__all__ = ["EpisodicCue"]
