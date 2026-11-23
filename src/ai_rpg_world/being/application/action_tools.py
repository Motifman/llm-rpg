"""行動の選択肢を、LLM のツールと、場面に置く候補表にする。"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from typing import Any

from ai_rpg_world.being.application.episode_recall_tool import episode_recall_description, episode_recall_parameters
from ai_rpg_world.being.application.memo_argument import memo_field_property
from ai_rpg_world.being.application.name_forms import name_forms
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
)

NameRechooser = Callable[[str, str, Mapping[str, str | None], str | None], str | None]

CANDIDATE_TABLE_HEADING = "現在選べる対象引数"
FREE_TEXT_WRITES = "{writes}を書く"
CANDIDATE_TABLE_NOTE = "※ 一覧にあることは操作の成功を保証しない。現在の状態や前提条件によって失敗する場合がある。"
DETAILS = "details"
HIDDEN_TEXT = "本文"
_INNER_THOUGHT_MAX_LENGTH = 500


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
        # 番号は表に出る候補の人だけで数える。いまはできない理由にだけ出る人を数えると、表に 1 人しか出ないのに番号が付く。
        self._people = PeopleCalledApart(
            name_for,
            tuple(
                p
                for choice in choices.choices
                for value in choice.values
                if isinstance(value, PickOne)
                for p in value.people()
            ),
        )
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

    def with_names_matched(
        self, tool_name: str, arguments: Mapping[str, object], rechoose: NameRechooser
    ) -> dict[str, object]:
        """候補から選ぶ値を、表記の崩れを直して候補の名前に合わせる。当たらない名前だけを ``rechoose`` に回し、
        名前が返れば置き換える。出していないツールの名前なら、そのまま返す。
        """
        matched = {k: (dict(v) if k == DETAILS and isinstance(v, Mapping) else v) for k, v in arguments.items()}
        choice = next((c for c in self._choices.choices if c.name == tool_name), None)
        if choice is not None:
            self._match(choice.values, choice.takes_details, matched, rechoose, None)
        return matched

    def _match(
        self,
        values: Sequence[ChoiceValue],
        takes_details: bool,
        arguments: dict[str, object],
        rechoose: NameRechooser,
        parent: str | None,
    ) -> None:
        for value in values:
            if isinstance(value, FreeText):
                continue
            # move_from と同じ置き場所を見る。上の段が details に勝ち、details を取らない行動では details を捨てる。
            place = arguments if value.name in arguments else (arguments.get(DETAILS) if takes_details else None)
            written = place.get(value.name) if isinstance(place, dict) else None
            by_label = {self._label(c.label): c for c in value.candidates}
            if not isinstance(place, dict) or not isinstance(written, str) or not written.strip() or not by_label:
                continue
            name = next((form for form in name_forms(written) if form in by_label), None)
            if name is None:
                name = rechoose(written, value.label, {n: self._described(c) for n, c in by_label.items()}, parent)
            if name is None or name not in by_label:
                continue
            place[value.name] = name
            self._match(by_label[name].values, takes_details, arguments, rechoose, name)

    def candidate_table(self) -> Description | None:
        lines = [
            f"- {choice.name}.{name}{'' if parent is None else f' ({_quoted(parent)})'}: {shown}"
            for choice in self._choices.choices
            for name, parent, shown in self._picks(choice.values, frozenset(o.name for o in choice.outline), None)
        ]
        if not lines:
            return None
        return Description(heading=CANDIDATE_TABLE_HEADING, text="\n".join((*lines, CANDIDATE_TABLE_NOTE)))

    def _definition(self, choice: ActionChoice) -> dict[str, Any]:
        properties: dict[str, Any] = {
            o.name: {
                "type": "string",
                "description": o.label,
                **({} if o.max_length is None else {"maxLength": o.max_length}),
            }
            for o in choice.outline
        }
        required = [o.name for o in choice.outline if o.required]
        inner_thought = self._being_tools.inner_thought
        memo = self._being_tools.memo
        reserved = {name for name in (DETAILS, inner_thought, memo) if name is not None} & set(properties)
        if reserved:
            raise ValueError(f"{choice.name!r} has outline names reserved by the Being: {sorted(reserved)}")
        if choice.takes_details:
            properties[DETAILS] = {
                "type": "object",
                "description": "操作が求める引数。",
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
            f"{choice.label}。候補のある引数には【{CANDIDATE_TABLE_HEADING}】の文字をそのまま書く。",
            {"type": "object", "properties": properties, "required": required},
        )

    def _picks(
        self, values: Sequence[ChoiceValue], outlined: frozenset[str], parent: str | None
    ) -> Iterator[tuple[str, str | None, str]]:
        for value in values:
            name = value.name if value.name in outlined else f"{DETAILS}.{value.name}"
            if isinstance(value, FreeText):
                if value.writes is not None:
                    yield name, parent, FREE_TEXT_WRITES.format(writes=value.writes)
                continue
            labels = tuple(dict.fromkeys(self._label(c.label) for c in value.candidates))
            if labels:
                yield name, parent, ", ".join(_quoted(label) for label in labels)
            for candidate in value.candidates:
                yield from self._picks(candidate.values, outlined, self._label(candidate.label))

    def _described(self, candidate: Candidate) -> str | None:
        """候補の下で選べるものを説明にする。名前だけでは、意味を推し量る材料が無い。"""
        labels = [self._label(c.label) for v in candidate.values if isinstance(v, PickOne) for c in v.candidates]
        return "、".join(labels) or None

    def _label(self, label: str | PersonInText) -> str:
        return self._people.name_of(label) if isinstance(label, PersonInText) else label

    def _person_or_value(self, value: object) -> object:
        person = self._people.person_named(value) if isinstance(value, str) else None
        return value if person is None else {"person": person.handle}


def _quoted(text: str) -> str:
    return json.dumps(text, ensure_ascii=False)


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
