"""PersonaPromptPolicy — どの persona section を system prompt にレンダリングするか制御。

DDD 再編 (Issue #470 Phase 1 PR4): 元 ``application/llm/contracts/persona.py``
から domain に昇格。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PersonaPromptPolicy:
    """Controls which persona sections are rendered into the system prompt."""

    include_background: bool = True
    include_traits: bool = True
    include_values: bool = True
    include_fears: bool = True
    include_taboos: bool = True
    include_fragmented_memories: bool = True
    include_behavioral_rules: bool = True
    include_relationship_hints: bool = True
    max_items_per_section: int = 6

    def __post_init__(self) -> None:
        for name in (
            "include_background",
            "include_traits",
            "include_values",
            "include_fears",
            "include_taboos",
            "include_fragmented_memories",
            "include_behavioral_rules",
            "include_relationship_hints",
        ):
            if not isinstance(getattr(self, name), bool):
                raise TypeError(f"{name} must be bool")
        if not isinstance(self.max_items_per_section, int):
            raise TypeError("max_items_per_section must be int")
        if self.max_items_per_section < 1:
            raise ValueError("max_items_per_section must be positive")


__all__ = ["PersonaPromptPolicy"]
