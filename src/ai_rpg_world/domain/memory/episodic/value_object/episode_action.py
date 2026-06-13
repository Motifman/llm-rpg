"""EpisodeAction — どう行動したか (ツール名 + 正規化引数の要約)。

DDD 再編 (Issue #470 Phase 1 PR2): 元 ``application/llm/contracts/episodic_memory.py``
から domain に昇格。
"""

from __future__ import annotations

from dataclasses import dataclass

from ai_rpg_world.domain.memory.episodic.value_object._validators import (
    optional_non_blank,
    reject_blank,
)


@dataclass(frozen=True)
class EpisodeAction:
    """どう行動したか（ツール名と正規化済み引数の要約）。"""

    tool_name: str
    canonical_arguments_text: str | None = None

    def __post_init__(self) -> None:
        tn = reject_blank("tool_name", self.tool_name)
        object.__setattr__(self, "tool_name", tn)
        cat = optional_non_blank("canonical_arguments_text", self.canonical_arguments_text)
        object.__setattr__(self, "canonical_arguments_text", cat)


__all__ = ["EpisodeAction"]
