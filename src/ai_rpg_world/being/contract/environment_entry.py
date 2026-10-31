"""環境に入るときに一度だけ渡す取り決め。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ai_rpg_world.being.contract.errors import (
    ContractViolation,
    require_optional_text,
    require_text,
)


@dataclass(frozen=True, kw_only=True)
class Introduction:
    """入るときに、最初から知っている相手として紹介される人。

    ``relation_note`` は「あなたと同じ側」のような、環境が描いた関係の文。
    """

    name: str
    relation_note: str | None = None

    def __post_init__(self) -> None:
        require_text(self.name, "name")
        require_optional_text(self.relation_note, "relation_note")


@dataclass(frozen=True, kw_only=True)
class EnvironmentEntry:
    """Being の名前は環境が付けず、Being が自分の名前 (``Persona.name``) で入る (design_decisions D1928-3)。

    紹介されなかった相手は、会うまで Being にとって居ないのと同じになる。
    """

    environment_name: str
    imposed_goal: str | None = None
    introductions: Sequence[Introduction] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        require_text(self.environment_name, "environment_name")
        require_optional_text(self.imposed_goal, "imposed_goal")
        introductions = tuple(self.introductions)
        if not all(isinstance(i, Introduction) for i in introductions):
            raise ContractViolation("introductions must be Introduction items")
        names = [i.name for i in introductions]
        if len(set(names)) != len(names):
            raise ContractViolation("introductions must not repeat a name")
        object.__setattr__(self, "introductions", introductions)
