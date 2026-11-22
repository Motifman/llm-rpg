"""人のプレースホルダーを持つ観測の本文。

環境は、文に人の名前を文字として入れず、プレースホルダーと人の印で渡す。どの呼び方で
覚えるかは、受け手の Being が決める。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from string import Formatter
from types import MappingProxyType
from typing import final

from ai_rpg_world.being.contract.errors import ContractViolation, require_optional_text, require_text


@final
@dataclass(frozen=True)
class PersonInText:
    """``handle`` は、同じ環境の中で 1 人をずっと指す番号。名前ではない。

    ``visible_name`` は、受け手に名前が見えているときだけ持つ。見えなければ None。
    """

    handle: int
    appearance: str
    visible_name: str | None

    def __post_init__(self) -> None:
        if isinstance(self.handle, bool) or not isinstance(self.handle, int) or self.handle < 0:
            raise ContractViolation("handle must be a non-negative int")
        require_text(self.appearance, "appearance")
        require_optional_text(self.visible_name, "visible_name")


@final
@dataclass(frozen=True)
class UnidentifiedPerson:
    """受け手が見分けられない人。印を持たない。"""


PersonPlaceholderValue = PersonInText | UnidentifiedPerson


@final
@dataclass(frozen=True)
class TextWithPeople:
    """``template`` のプレースホルダーは ``{名前}`` だけで、``people`` の鍵と過不足なく揃う。"""

    template: str
    people: Mapping[str, PersonPlaceholderValue]

    def __post_init__(self) -> None:
        require_text(self.template, "template")
        placeholders = _person_placeholders_in(self.template)
        if placeholders != set(self.people):
            raise ContractViolation(
                f"placeholders {sorted(placeholders)} and people {sorted(self.people)} differ in {self.template!r}"
            )
        if not all(isinstance(person, (PersonInText, UnidentifiedPerson)) for person in self.people.values()):
            raise ContractViolation("people must be PersonInText or UnidentifiedPerson")
        object.__setattr__(self, "people", MappingProxyType(dict(self.people)))

    def __hash__(self) -> int:
        # people を書き換えられない MappingProxyType で持つと、dataclass の既定のハッシュが使えない。
        return hash((self.template, frozenset(self.people.items())))


def _person_placeholders_in(template: str) -> frozenset[str]:
    try:
        parsed = list(Formatter().parse(template))
    except ValueError as error:
        raise ContractViolation(f"unbalanced braces in {template!r}") from error
    placeholders: set[str] = set()
    rebuilt: list[str] = []
    for literal, field_name, _, _ in parsed:
        rebuilt.append(literal.replace("{", "{{").replace("}", "}}"))
        if field_name is None:
            continue
        if not field_name.isidentifier():
            raise ContractViolation(f"placeholder {{{field_name}}} in {template!r} is not a named person placeholder")
        rebuilt.append(f"{{{field_name}}}")
        placeholders.add(field_name)
    # parse は空の書式指定 ({actor:}) を書式指定なしと区別しないので、組み直して元の文と比べる。
    if "".join(rebuilt) != template:
        raise ContractViolation(f"{template!r} has a placeholder with a conversion or format spec")
    return frozenset(placeholders)
