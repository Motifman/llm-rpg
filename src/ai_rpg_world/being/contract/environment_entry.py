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
    """``self_name`` は、Being が自分の書いた文の中の自分を見分けるのに使う。
    観測の主体や宛先は環境が判定して観測に書くが、予期や信念の文の中の名前は
    環境には分からない。

    紹介されなかった相手は、会うまで Being にとって居ないのと同じになる。
    """

    environment_name: str
    self_name: str
    imposed_goal: str | None = None
    introductions: Sequence[Introduction] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        require_text(self.environment_name, "environment_name")
        require_text(self.self_name, "self_name")
        require_optional_text(self.imposed_goal, "imposed_goal")
        introductions = tuple(self.introductions)
        if not all(isinstance(i, Introduction) for i in introductions):
            raise ContractViolation("introductions must be Introduction items")
        names = [i.name for i in introductions]
        if self.self_name in names:
            raise ContractViolation("introductions must not include self")
        if len(set(names)) != len(names):
            raise ContractViolation("introductions must not repeat a name")
        object.__setattr__(self, "introductions", introductions)
