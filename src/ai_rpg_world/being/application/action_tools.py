"""行動の選択肢を、LLM のツールと、場面に置く候補表にする。"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from itertools import product
from typing import Any

from ai_rpg_world.being.application.episode_recall_tool import episode_recall_description, episode_recall_parameters
from ai_rpg_world.being.application.memo_argument import memo_field_property
from ai_rpg_world.being.application.people_called_apart import PeopleCalledApart
from ai_rpg_world.being.contract import (
    ActionChoice,
    ActionChoices,
    AgentMove,
    Candidate,
    ChoiceValue,
    Description,
    FreeText,
    FrozenJsonObject,
    OfferedBeingTools,
    PersonInText,
    PersonPlaceholderValue,
    PickOne,
    TextWithPeople,
    UnavailableAction,
)

CANDIDATE_TABLE_HEADING = "行動の候補"
DETAILS = "details"
HIDDEN_TEXT = "本文"
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
        *,
        recall_limit: int,
    ) -> None:
        self._choices = choices
        self._being_tools = being_tools
        self._people = PeopleCalledApart(name_for, choices.people())
        self._recall_limit = recall_limit

    def definitions(self) -> tuple[dict[str, Any], ...]:
        actions = tuple(self._definition(choice) for choice in self._choices.choices)
        recall = self._being_tools.episode_recall
        if recall is None:
            return actions
        return (
            *actions,
            _function(
                recall, episode_recall_description(self._recall_limit), episode_recall_parameters(self._recall_limit)
            ),
        )

    def tool_names(self) -> tuple[str, ...]:
        recall = self._being_tools.episode_recall
        return tuple(choice.name for choice in self._choices.choices) + (() if recall is None else (recall,))

    def move_from(self, *, call_id: str, tool_name: str, arguments: Mapping[str, object]) -> AgentMove | None:
        """出していないツールの名前なら None。

        世界がツールの書式を知らずに済むよう、``details`` を外して平らに並べ、候補から選ぶ値の人の呼び方は
        人の印に戻す。``details`` の中と上の段で名前が重なれば、上の段を使う。
        """
        choice = next((c for c in self._choices.choices if c.name == tool_name), None)
        if choice is None:
            return None
        given = dict(arguments)
        thought = given.pop(self._being_tools.inner_thought, None) if self._being_tools.inner_thought else None
        if self._being_tools.memo is not None:
            given.pop(self._being_tools.memo, None)
        details = given.pop(DETAILS, None) if choice.takes_details else None
        flat = {**(details if isinstance(details, Mapping) else {}), **given}
        picked = _picked_names(choice.values)
        return AgentMove(
            call_id=call_id,
            tool_name=tool_name,
            arguments=FrozenJsonObject(
                {name: self._person_or_value(value) if name in picked else value for name, value in flat.items()}
            ),
            inner_thought=thought if isinstance(thought, str) and thought.strip() else None,
        )

    def call_text(self, tool_name: str, arguments: Mapping[str, object]) -> str | None:
        """出していないツールの名前なら None。

        候補から選んだ値だけを引用し、ほかは見取り図の伏せる言葉 (無ければ「本文」) で伏せる。自由に書いた文を引用すると、
        手本として写されるため。
        独白とメモは別の行や欄に出るので出さない。
        """
        choice = next((c for c in self._choices.choices if c.name == tool_name), None)
        if choice is None:
            return None
        picked = _picked_names(choice.values)
        hidden = {self._being_tools.inner_thought, self._being_tools.memo}
        # 古い run と同じく、LLM が書いた順によらない並びにする。並びが揺れると、写す手本として読みにくい。
        order = [o.name for o in choice.outline]
        given = sorted(
            ((name, value) for name, value in arguments.items() if name not in hidden),
            key=lambda item: (0, order.index(item[0]), "") if item[0] in order else (1, 0, item[0]),
        )
        quoted = [(name, value) for name, value in given if name in picked and isinstance(value, str)]
        hidden_as = {o.name: o.hidden_as for o in choice.outline if o.hidden_as is not None}
        parts = [f"{name}={json.dumps(value, ensure_ascii=False)}" for name, value in quoted] + [
            f"{name}={hidden_as.get(name, HIDDEN_TEXT)}" for name, value in given if (name, value) not in quoted
        ]
        return f"{tool_name}({', '.join(parts)})"

    def candidate_table(self) -> Description:
        return Description(
            heading=CANDIDATE_TABLE_HEADING,
            text="\n".join(line for choice in self._choices.choices for line in self._table_lines(choice)),
        )

    def _definition(self, choice: ActionChoice) -> dict[str, Any]:
        properties: dict[str, Any] = {o.name: {"type": "string", "description": o.label} for o in choice.outline}
        required = [o.name for o in choice.outline if o.required]
        inner_thought = self._being_tools.inner_thought
        memo = self._being_tools.memo
        reserved = {name for name in (DETAILS, inner_thought, memo) if name is not None} & set(properties)
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
        if memo is not None:
            properties[memo] = memo_field_property(episode_source_offered=self._being_tools.episode_index_shown)
        return _function(
            choice.name,
            f"{choice.label}。候補のある引数には【{CANDIDATE_TABLE_HEADING}】の文字をそのまま書く。"
            f"いまはできないことも【{CANDIDATE_TABLE_HEADING}】に出る。",
            {"type": "object", "properties": properties, "required": required},
        )

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

    def _person_or_value(self, value: object) -> object:
        person = self._people.person_named(value) if isinstance(value, str) else None
        return value if person is None else {"person": person.handle}


def _function(name: str, description: str, parameters: dict[str, Any]) -> dict[str, Any]:
    return {"type": "function", "function": {"name": name, "description": description, "parameters": parameters}}


def _picked_names(values: Sequence[ChoiceValue]) -> frozenset[str]:
    names: set[str] = set()
    for value in values:
        if isinstance(value, PickOne):
            names.add(value.name)
            for candidate in value.candidates:
                names |= _picked_names(candidate.values)
    return frozenset(names)


__all__ = ["CANDIDATE_TABLE_HEADING", "DETAILS", "ActionTools"]
