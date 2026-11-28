from __future__ import annotations

import json
import random
import re
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, final

from ai_rpg_world.being.application.action_tools import (
    AVAILABLE_NOW,
    CANDIDATE_TABLE_HEADING,
    DETAILS,
    NOTHING_AVAILABLE,
    UNAVAILABLE_NOW,
)
from ai_rpg_world.being.application.choose_action import (
    ActionChoosingCompletion,
    ActionChoosingReply,
    ToolCallReply,
)

RANDOM_TEXT = "でたらめに選んだ行動"
_TABLE_HEADING = f"【{CANDIDATE_TABLE_HEADING}】"
_LEFT_UNWRITTEN = frozenset({"memo", "say_inline"})
_ROW_HEADING = re.compile(r"^- (?P<tool>[a-z_]+)\.(?P<argument>[a-z_.]+)(?: \((?P<parent>\".*\")\))?:(?P<rest>.*)$")
_WHOLE_CHOICE_UNAVAILABLE = re.compile(rf"^- (?P<tool>[a-z_]+): {UNAVAILABLE_NOW}（.*）$")
_QUOTED = re.compile(r'^(?P<value>"(?:[^"\\]|\\.)*")(?:（.*）)?$')
_OPTIONAL_PROBABILITY = 0.5
_PICKING_TOOL_WEIGHT = 4


@dataclass
class _Row:
    available: list[str] = field(default_factory=list)
    writes: bool = False


class _Unreadable(Exception):
    pass


def _unquoted(quoted: str) -> str:
    # 候補表は候補を JSON の文字列で書くので、引用符と \ の書き戻しも JSON で読む
    try:
        value = json.loads(quoted)
    except json.JSONDecodeError as error:
        raise _Unreadable from error
    if not isinstance(value, str):
        raise _Unreadable
    return value


@dataclass(frozen=True)
class CandidateTable:
    rows: Mapping[tuple[str, str, str | None], _Row]
    unavailable_tools: frozenset[str]
    unreadable_lines: tuple[str, ...]

    @classmethod
    def read(cls, text: str) -> CandidateTable:
        start = text.find(_TABLE_HEADING)
        rows: dict[tuple[str, str, str | None], _Row] = {}
        unavailable: set[str] = set()
        unreadable: list[str] = []
        if start < 0:
            return cls(rows, frozenset(), ())
        current: _Row | None = None
        section: str | None = None
        for line in text[start + len(_TABLE_HEADING) :].splitlines()[1:]:
            if not line.strip() or line.startswith("※"):
                break
            try:
                current, section = cls._read_line(line, rows, unavailable, current, section)
            except _Unreadable:
                if line not in unreadable:
                    unreadable.append(line)
        return cls(rows, frozenset(unavailable), tuple(unreadable))

    @staticmethod
    def _read_line(
        line: str,
        rows: dict[tuple[str, str, str | None], _Row],
        unavailable: set[str],
        current: _Row | None,
        section: str | None,
    ) -> tuple[_Row | None, str | None]:
        stripped = line.strip()
        if whole := _WHOLE_CHOICE_UNAVAILABLE.match(line):
            unavailable.add(whole.group("tool"))
            return None, None
        if heading := _ROW_HEADING.match(line):
            parent = None if heading.group("parent") is None else _unquoted(heading.group("parent"))
            row = rows.setdefault((heading.group("tool"), heading.group("argument"), parent), _Row())
            row.writes = bool(heading.group("rest").strip())
            return row, None
        if stripped in (f"{AVAILABLE_NOW}:", f"{UNAVAILABLE_NOW}:"):
            return current, stripped
        if current is None or section is None:
            raise _Unreadable
        if stripped == NOTHING_AVAILABLE:
            return current, section
        quoted = _QUOTED.match(stripped)
        if quoted is None:
            raise _Unreadable
        value = _unquoted(quoted.group("value"))
        if section == f"{AVAILABLE_NOW}:":
            current.available.append(value)
        return current, section

    def row(self, tool: str, argument: str, chosen: Sequence[str]) -> _Row | None:
        for parent in (*reversed(chosen), None):
            found = self.rows.get((tool, argument, parent))
            if found is not None:
                return found
        return None

    def details_of(self, tool: str, chosen: Sequence[str]) -> list[str]:
        names = {
            argument[len(DETAILS) + 1 :]
            for (row_tool, argument, parent) in self.rows
            if row_tool == tool and argument.startswith(f"{DETAILS}.") and (parent is None or parent in chosen)
        }
        return sorted(names)


class _Infeasible(Exception):
    pass


def choose_random_call(rng: random.Random, user_text: str, tools: Sequence[Mapping[str, Any]]) -> dict[str, Any] | None:
    table = CandidateTable.read(user_text)
    feasible: list[dict[str, Any]] = []
    weights: list[int] = []
    for tool in tools:
        function = tool.get("function") or {}
        name = str(function.get("name") or "")
        if name in table.unavailable_tools:
            continue
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
    arguments: dict[str, Any] = {}
    chosen: list[str] = []
    picked = False
    for name, schema in properties.items():
        if name in _LEFT_UNWRITTEN or name == DETAILS:
            continue
        if schema.get("type") == "array":
            arguments[name] = [RANDOM_TEXT]
            continue
        row = table.row(tool, name, chosen)
        if row is not None and not row.writes:
            if not row.available:
                if name in required:
                    raise _Infeasible
                continue
            value = rng.choice(row.available)
            arguments[name] = value
            chosen.append(value)
            picked = True
        # 候補の無い値の引数は表に行が出ず、書く値の引数と見分けられない。決まった文を書き、世界が断る道も試す
        elif name in required or row is not None or rng.random() < _OPTIONAL_PROBABILITY:
            arguments[name] = RANDOM_TEXT
    if DETAILS in properties:
        details = _details(rng, table, tool, chosen)
        if details:
            arguments[DETAILS] = details
    return arguments, picked


def _details(rng: random.Random, table: CandidateTable, tool: str, chosen: list[str]) -> dict[str, str]:
    details: dict[str, str] = {}
    looked_at: set[str] = set()
    # 値の下にさらに引数が続くことがあるので、選んだ値を親に加えながら、新しい引数が見つからなくなるまで探す
    while pending := [name for name in table.details_of(tool, chosen) if name not in looked_at]:
        for name in pending:
            looked_at.add(name)
            row = table.row(tool, f"{DETAILS}.{name}", chosen)
            if row is None:
                continue
            if row.writes:
                details[name] = RANDOM_TEXT
            elif row.available:
                details[name] = rng.choice(row.available)
                chosen.append(details[name])
            else:
                raise _Infeasible
    return details


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
