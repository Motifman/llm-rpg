"""環境が自分の言葉で書いた説明文と、それを渡す 2 つの並び。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ai_rpg_world.being.contract.errors import ContractViolation, require_text


@dataclass(frozen=True, kw_only=True)
class Description:
    """``heading`` は【】で囲まない語。囲むのは、Being が文にするときの書き方。

    Being は中身を読まず、どの並びで届いたかだけで置き場所を決める。
    """

    heading: str
    text: str

    def __post_init__(self) -> None:
        require_text(self.heading, "heading")
        require_text(self.text, "text")
        if any(c in self.heading for c in "【】\n"):
            raise ContractViolation("heading must not contain brackets or line breaks")


def _descriptions(items: Sequence[Description]) -> tuple[Description, ...]:
    descriptions = tuple(items)
    if not all(isinstance(d, Description) for d in descriptions):
        raise ContractViolation("descriptions must be Description items")
    headings = [d.heading for d in descriptions]
    repeated = sorted({h for h in headings if headings.count(h) > 1})
    if repeated:
        raise ContractViolation(f"descriptions must not repeat a heading: {repeated}")
    return descriptions


@dataclass(frozen=True)
class Orientation:
    """入るときに 1 回受け取る案内。世界の前提、場所の造り、環境の決まりなど。"""

    descriptions: Sequence[Description] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "descriptions", _descriptions(self.descriptions))


@dataclass(frozen=True)
class Scene:
    """毎ターン置き換わる、今見えている場面。現在地と周囲、選べる対象、知らせなど。"""

    descriptions: Sequence[Description] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "descriptions", _descriptions(self.descriptions))
