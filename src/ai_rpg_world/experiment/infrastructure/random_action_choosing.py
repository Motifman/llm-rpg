from __future__ import annotations

import json
import random
import re
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, final

from ai_rpg_world.being.application.action_tools import CANDIDATE_TABLE_HEADING, DETAILS, NOTHING_LISTED
from ai_rpg_world.being.application.choose_action import (
    ActionChoosingCompletion,
    ActionChoosingReply,
    ToolCallReply,
)

RANDOM_TEXT = "でたらめに選んだ行動"
_TABLE_HEADING = f"【{CANDIDATE_TABLE_HEADING}】"
_LEFT_UNWRITTEN = frozenset({"memo", "say_inline"})
_QUOTED_STRING = r'"(?:[^"\\]|\\.)*"'
_UNDER_A_NAME = re.compile(rf"^(?P<parent>{_QUOTED_STRING}): (?P<rest>.+)$")
_UNDER_A_TOOL = re.compile(rf"^(?P<tool>[a-z_]+)(?: (?P<parent>{_QUOTED_STRING}))?: (?P<rest>.+)$")
_TOOL_AT_THE_END = re.compile(r"^(?P<rest>.+) \((?P<tool>[a-z_]+)\)$")
_LISTED = re.compile(rf"(?P<value>{_QUOTED_STRING})(?: \((?P<asked>[^()]*)\))?(?:, |$)")
_ASKED_KEY = re.compile(rf"{DETAILS}\.(?P<key>[a-z_][a-z0-9_]*) に")
_QUOTED_ANYWHERE = re.compile(_QUOTED_STRING)
_PARENT_PROBABILITY = 0.7
_OPTIONAL_PROBABILITY = 0.5
_PICKING_TOOL_WEIGHT = 4


@dataclass
class _Listed:
    value: str
    asked_keys: tuple[str, ...] = ()


@dataclass
class _Row:
    listed: list[_Listed] = field(default_factory=list)


class _Unreadable(Exception):
    pass


def _unquoted(quoted: str) -> str:
    # 表は名前を JSON の文字列で書くので、引用符と \ の書き戻しも JSON で読む
    try:
        value = json.loads(quoted)
    except json.JSONDecodeError as error:
        raise _Unreadable from error
    if not isinstance(value, str):
        raise _Unreadable
    return value


def _listed(rest: str) -> list[_Listed]:
    found: list[_Listed] = []
    position = 0
    while position < len(rest):
        match = _LISTED.match(rest, position)
        if match is None or match.end() == position:
            raise _Unreadable
        keys = tuple(_ASKED_KEY.findall(match.group("asked") or ""))
        found.append(_Listed(_unquoted(match.group("value")), keys))
        position = match.end()
    return found


@dataclass(frozen=True)
class CandidateTable:
    """``under_names`` は「"カンテラ": …」の行、``under_tools`` は「vote "決めごと": …」「"籠": … (set_sub_location)」の行。"""

    under_names: Mapping[str, _Row]
    under_tools: Mapping[tuple[str, str | None], _Row]
    scene_names: tuple[str, ...]
    unreadable_lines: tuple[str, ...]

    @classmethod
    def read(cls, text: str) -> CandidateTable:
        start = text.find(_TABLE_HEADING)
        scene_names = tuple(
            dict.fromkeys(
                name
                for quoted in _QUOTED_ANYWHERE.findall(text if start < 0 else text[:start])
                for name in _names_in(quoted)
            )
        )
        under_names: dict[str, _Row] = {}
        under_tools: dict[tuple[str, str | None], _Row] = {}
        unreadable: list[str] = []
        if start < 0:
            return cls(under_names, under_tools, scene_names, ())
        for line in text[start + len(_TABLE_HEADING) :].splitlines()[1:]:
            if not line.strip() or line.startswith("※"):
                break
            if line == NOTHING_LISTED:
                continue
            try:
                cls._read_line(line, under_names, under_tools)
            except _Unreadable:
                if line not in unreadable:
                    unreadable.append(line)
        return cls(under_names, under_tools, scene_names, tuple(unreadable))

    @staticmethod
    def _read_line(line: str, under_names: dict[str, _Row], under_tools: dict[tuple[str, str | None], _Row]) -> None:
        if named := _UNDER_A_NAME.match(line):
            # 区画の行は、頭の名前が引数ではなく、後ろのツールの名前の最初の引数の候補を並べる
            if tagged := _TOOL_AT_THE_END.match(named.group("rest")):
                under_tools.setdefault((tagged.group("tool"), None), _Row()).listed += _listed(tagged.group("rest"))
                return
            under_names.setdefault(_unquoted(named.group("parent")), _Row()).listed += _listed(named.group("rest"))
            return
        if tool := _UNDER_A_TOOL.match(line):
            parent = None if tool.group("parent") is None else _unquoted(tool.group("parent"))
            under_tools.setdefault((tool.group("tool"), parent), _Row()).listed += _listed(tool.group("rest"))
            return
        raise _Unreadable

    def tool_values(self, tool: str) -> list[str]:
        return [
            parent if parent is not None else listed.value
            for (row_tool, parent), row in self.under_tools.items()
            if row_tool == tool
            for listed in (row.listed[:1] if parent is not None else row.listed)
        ]

    def below(self, tool: str, chosen: str) -> _Row | None:
        return self.under_tools.get((tool, chosen)) or self.under_names.get(chosen)


def _names_in(quoted: str) -> tuple[str, ...]:
    try:
        return (_unquoted(quoted),)
    except _Unreadable:
        return ()


class _Infeasible(Exception):
    pass


def choose_random_call(rng: random.Random, user_text: str, tools: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    table = CandidateTable.read(user_text)
    feasible: list[dict[str, Any]] = []
    weights: list[int] = []
    for tool in tools:
        function = tool.get("function") or {}
        name = str(function.get("name") or "")
        parameters = function.get("parameters") or {}
        try:
            arguments, picked = _arguments(rng, table, name, parameters)
        except _Infeasible:
            continue
        feasible.append({"name": name, "arguments": arguments})
        weights.append(_PICKING_TOOL_WEIGHT if picked else 1)
    if not feasible:
        return None
    return rng.choices(feasible, weights=weights)[0]


def _arguments(
    rng: random.Random, table: CandidateTable, tool: str, parameters: Mapping[str, Any]
) -> tuple[dict[str, Any], bool]:
    properties: Mapping[str, Any] = parameters.get("properties") or {}
    required = set(parameters.get("required") or ())
    written = [name for name in properties if name not in _LEFT_UNWRITTEN and name != DETAILS]
    arguments: dict[str, Any] = {}
    chosen: list[str] = []
    asked: tuple[str, ...] = ()
    picked = False
    for index, name in enumerate(written):
        schema = properties[name]
        if schema.get("type") == "array":
            arguments[name] = [RANDOM_TEXT]
            continue
        value, asked_here = _value(rng, table, tool, schema, chosen, has_next=index + 1 < len(written))
        if value is None and name not in required and rng.random() >= _OPTIONAL_PROBABILITY:
            continue
        if value is None:
            value = rng.choice(table.scene_names) if table.scene_names else RANDOM_TEXT
        else:
            picked = True
        if not isinstance(value, str):
            raise _Infeasible
        arguments[name] = value
        chosen.append(value)
        asked = asked_here or asked
    if DETAILS in properties and asked:
        arguments[DETAILS] = {key: rng.choice((RANDOM_TEXT, *table.scene_names)) for key in asked}
    return arguments, picked


def _value(
    rng: random.Random,
    table: CandidateTable,
    tool: str,
    schema: Mapping[str, Any],
    chosen: list[str],
    *,
    has_next: bool,
) -> tuple[str | None, tuple[str, ...]]:
    if schema.get("enum"):
        return rng.choice(list(schema["enum"])), ()
    if not chosen and (from_tool := table.tool_values(tool)):
        return rng.choice(from_tool), ()
    row = table.below(tool, chosen[-1]) if chosen else None
    if row is not None and row.listed:
        listed = rng.choice(row.listed)
        return listed.value, listed.asked_keys
    # 候補を並べない引数 (行き先・相手) は、操作の並ぶ対象か場面の名前から選ぶ。どちらも世界が断る道も試す
    parents = list(table.under_names)
    if has_next and parents and rng.random() < _PARENT_PROBABILITY:
        return rng.choice(parents), ()
    return None, ()


@final
class RandomActionChoosing(ActionChoosingCompletion):
    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)
        self._lock = threading.Lock()
        self._calls = 0

    def choose_action(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]], *, reasoning_off: bool
    ) -> ActionChoosingReply:
        with self._lock:
            self._calls += 1
            call = choose_random_call(self._rng, messages[-1]["content"], tools)
            call_id = f"random_{self._calls}"
        if call is None:
            return ActionChoosingReply(tool_call=None)
        return ActionChoosingReply(
            tool_call=ToolCallReply(tool_name=call["name"], arguments=call["arguments"], call_id=call_id)
        )
