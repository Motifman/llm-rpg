"""環境が毎ターン渡す、行動の選択肢 (design_decisions D2226)。

行動の種類ごとに 1 つの選択肢にし、相手は候補から選ぶ。値は、自由に書く文字 (``FreeText``) と、
候補から選ぶもの (``PickOne``) の 2 種類。いまはできない行動は候補に入れず、理由を付けて渡す。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Union

from ai_rpg_world.being.contract.errors import ContractViolation, require_text
from ai_rpg_world.being.contract.text_with_people import PersonInText, TextWithPeople


def _require_name(value: object, field_name: str) -> None:
    if not isinstance(value, str) or not value.isascii() or not value.isidentifier():
        raise ContractViolation(f"{field_name} must be an ASCII identifier, got {value!r}")


def _require_label(value: object, field_name: str) -> None:
    if not isinstance(value, PersonInText):
        require_text(value, field_name)


def _label_key(label: str | PersonInText) -> object:
    return label.handle if isinstance(label, PersonInText) else label


@dataclass(frozen=True, kw_only=True)
class FreeText:
    name: str
    label: str

    def __post_init__(self) -> None:
        _require_name(self.name, "name")
        require_text(self.label, "label")


@dataclass(frozen=True, kw_only=True)
class Candidate:
    """人の候補は ``PersonInText`` で渡す。呼び方と、呼び方が重なったときの呼び分けは Being が決める。"""

    label: str | PersonInText
    values: Sequence[ChoiceValue] = field(default_factory=tuple)
    count: int = 1

    def __post_init__(self) -> None:
        _require_label(self.label, "label")
        object.__setattr__(self, "values", _values(self.values))
        if isinstance(self.count, bool) or not isinstance(self.count, int) or self.count < 1:
            raise ContractViolation(f"count must be a positive int, got {self.count!r}")


@dataclass(frozen=True, kw_only=True)
class PickOne:
    name: str
    label: str
    candidates: Sequence[Candidate]

    def __post_init__(self) -> None:
        _require_name(self.name, "name")
        require_text(self.label, "label")
        candidates = tuple(self.candidates)
        if not all(isinstance(c, Candidate) for c in candidates):
            raise ContractViolation("candidates must be Candidate items")
        keys = [_label_key(c.label) for c in candidates]
        if len(set(keys)) != len(keys):
            raise ContractViolation(f"candidates must not repeat a label in {self.name!r}")
        object.__setattr__(self, "candidates", candidates)


ChoiceValue = Union[FreeText, PickOne]


def _values(items: Sequence[ChoiceValue]) -> tuple[ChoiceValue, ...]:
    values = tuple(items)
    if not all(isinstance(v, (FreeText, PickOne)) for v in values):
        raise ContractViolation("values must be FreeText or PickOne items")
    names = [v.name for v in values]
    if len(set(names)) != len(names):
        raise ContractViolation(f"values must not repeat a name: {names}")
    return values


@dataclass(frozen=True, kw_only=True)
class UnavailableAction:
    """``picked`` は、選べたなら選んだはずの候補の道筋。空なら行動ごと選べない。"""

    picked: Sequence[str | PersonInText]
    reason: str | TextWithPeople

    def __post_init__(self) -> None:
        picked = tuple(self.picked)
        for label in picked:
            _require_label(label, "picked")
        if not isinstance(self.reason, TextWithPeople):
            require_text(self.reason, "reason")
        object.__setattr__(self, "picked", picked)

    def covers_whole_action(self) -> bool:
        return not self.picked


@dataclass(frozen=True, kw_only=True)
class ActionChoice:
    """``name`` は LLM のツールの名前になる。環境は、選べるものが無いターンも同じ顔ぶれで渡す。"""

    name: str
    label: str
    values: Sequence[ChoiceValue] = field(default_factory=tuple)
    unavailable: Sequence[UnavailableAction] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        _require_name(self.name, "name")
        require_text(self.label, "label")
        values = _values(self.values)
        unavailable = tuple(self.unavailable)
        if not all(isinstance(u, UnavailableAction) for u in unavailable):
            raise ContractViolation("unavailable must be UnavailableAction items")
        if any(u.covers_whole_action() for u in unavailable) and _offers_candidates(values):
            raise ContractViolation(f"{self.name!r} is unavailable as a whole but still offers candidates")
        object.__setattr__(self, "values", values)
        object.__setattr__(self, "unavailable", unavailable)

    def can_be_chosen(self) -> bool:
        if any(u.covers_whole_action() for u in self.unavailable):
            return False
        return all(v.candidates for v in self.values if isinstance(v, PickOne))


def _offers_candidates(values: tuple[ChoiceValue, ...]) -> bool:
    return any(v.candidates for v in values if isinstance(v, PickOne))


@dataclass(frozen=True)
class ActionChoices:
    choices: Sequence[ActionChoice]

    def __post_init__(self) -> None:
        choices = tuple(self.choices)
        if not all(isinstance(c, ActionChoice) for c in choices):
            raise ContractViolation("choices must be ActionChoice items")
        names = [c.name for c in choices]
        if len(set(names)) != len(names):
            raise ContractViolation(f"choices must not repeat a name: {names}")
        object.__setattr__(self, "choices", choices)
