"""行動の選択肢を、LLM のツールと、場面に置く候補表にする。"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from itertools import product
from typing import Any

from ai_rpg_world.being.application.people_called_apart import PeopleCalledApart
from ai_rpg_world.being.contract import (
    ActionChoice,
    ActionChoices,
    Candidate,
    ChoiceValue,
    Description,
    FreeText,
    OfferedBeingTools,
    PersonInText,
    PersonPlaceholderValue,
    TextWithPeople,
    UnavailableAction,
)

CANDIDATE_TABLE_HEADING = "行動の候補"
DETAILS = "details"
_INNER_THOUGHT_MAX_LENGTH = 500

_Pairs = tuple[tuple[str, str], ...]


class ActionTools:
    """候補はターンごとに変わるので、ツールの説明や enum には入れず、候補表に出す。ツールの定義が変わると
    プレフィックスのキャッシュが切れる。
    """

    def __init__(
        self,
        choices: ActionChoices,
        being_tools: OfferedBeingTools,
        name_for: Callable[[PersonPlaceholderValue], str],
    ) -> None:
        self._choices = choices
        self._being_tools = being_tools
        self._people = PeopleCalledApart(name_for, choices.people())

    def definitions(self) -> tuple[dict[str, Any], ...]:
        return tuple(self._definition(choice) for choice in self._choices.choices)

    def candidate_table(self) -> Description:
        return Description(
            heading=CANDIDATE_TABLE_HEADING,
            text="\n".join(line for choice in self._choices.choices for line in self._table_lines(choice)),
        )

    def _definition(self, choice: ActionChoice) -> dict[str, Any]:
        properties: dict[str, Any] = {o.name: {"type": "string", "description": o.label} for o in choice.outline}
        required = [o.name for o in choice.outline if o.required]
        inner_thought = self._being_tools.inner_thought
        reserved = {name for name in (DETAILS, inner_thought) if name is not None} & set(properties)
        if reserved:
            raise ValueError(f"{choice.name!r} has outline names reserved by the Being: {sorted(reserved)}")
        if choice.takes_details:
            properties[DETAILS] = {
                "type": "object",
                "description": f"操作が求める引数。要るものは【{CANDIDATE_TABLE_HEADING}】に {DETAILS}.名前 の形で出る。",
                "additionalProperties": {"type": "string"},
            }
        if inner_thought is not None:
            properties[inner_thought] = {
                "type": "string",
                "description": "この行動を選ぶ直前の、あなた自身の頭の中の独白を一文で。書き方は【行動のしかた】。",
                "maxLength": _INNER_THOUGHT_MAX_LENGTH,
                "minLength": 1,
            }
            required.append(inner_thought)
        return {
            "type": "function",
            "function": {
                "name": choice.name,
                "description": (
                    f"{choice.label}。候補のある引数には【{CANDIDATE_TABLE_HEADING}】の文字をそのまま書く。"
                    f"いまはできないことも【{CANDIDATE_TABLE_HEADING}】に出る。"
                ),
                "parameters": {"type": "object", "properties": properties, "required": required},
            },
        }

    def _table_lines(self, choice: ActionChoice) -> Iterator[str]:
        yield f"{choice.name}（{choice.label}）"
        if choice.can_be_chosen():
            outlined = frozenset(o.name for o in choice.outline)
            for pairs in self._alternatives(choice.values, outlined):
                yield "- " + (", ".join(f"{name}: {text}" for name, text in pairs) or "選ぶ値は無い")
        elif not any(u.covers_whole_action() for u in choice.unavailable):
            yield "- いまは候補が無い"
        for unavailable in choice.unavailable:
            yield self._unavailable_line(unavailable)

    def _alternatives(self, values: Sequence[ChoiceValue], outlined: frozenset[str]) -> Iterator[_Pairs]:
        per_value = [list(self._value_alternatives(value, outlined)) for value in values]
        for combination in product(*per_value):
            yield tuple(pair for pairs in combination for pair in pairs)

    def _value_alternatives(self, value: ChoiceValue, outlined: frozenset[str]) -> Iterator[_Pairs]:
        name = value.name if value.name in outlined else f"{DETAILS}.{value.name}"
        if isinstance(value, FreeText):
            yield ((name, f"（{value.label}を書く）"),)
            return
        if all(not c.values for c in value.candidates):
            yield ((name, " / ".join(self._candidate_text(c) for c in value.candidates)),)
            return
        for candidate in value.candidates:
            head = ((name, self._candidate_text(candidate)),)
            for rest in self._alternatives(candidate.values, outlined):
                yield head + rest

    def _candidate_text(self, candidate: Candidate) -> str:
        label = self._label(candidate.label)
        return label if candidate.count == 1 else f"{label} ×{candidate.count}"

    def _unavailable_line(self, unavailable: UnavailableAction) -> str:
        reason = unavailable.reason
        reason_text = self._people.text_of(reason) if isinstance(reason, TextWithPeople) else reason
        if unavailable.covers_whole_action():
            return f"- いまはできない: {reason_text}"
        path = " / ".join(self._label(label) for label in unavailable.picked)
        return f"- いまはできない: {path} — {reason_text}"

    def _label(self, label: str | PersonInText) -> str:
        return self._people.name_of(label) if isinstance(label, PersonInText) else label


__all__ = ["CANDIDATE_TABLE_HEADING", "DETAILS", "ActionTools"]
