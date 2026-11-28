"""でたらめでも世界に実在する行動を試すよう、必須の引数の「いまできる」が空のツールは選ばない (D1557)。"""

from __future__ import annotations

import random
import re
import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, final

from ai_rpg_world.being.application.choose_action import (
    ActionChoosingCompletion,
    ActionChoosingReply,
    ToolCallReply,
)

RANDOM_TEXT = "でたらめに選んだ行動"
_TABLE_HEADING = "【現在選べる対象引数】"
_DETAILS = "details"
_LEFT_UNWRITTEN = frozenset({"memo", "say_inline"})
_ROW_HEADING = re.compile(r'^- (?P<tool>[a-z_]+)\.(?P<argument>[a-z_.]+)(?: \("(?P<parent>.*)"\))?:(?P<rest>.*)$')
_WHOLE_CHOICE_UNAVAILABLE = re.compile(r"^- (?P<tool>[a-z_]+): いまできない（.*）$")
_QUOTED = re.compile(r'^"(?P<value>.*)"(?:（.*）)?$')
_OPTIONAL_PROBABILITY = 0.5
_PICKING_TOOL_WEIGHT = 4


@dataclass
class _Row:
    available: list[str] = field(default_factory=list)
    writes: bool = False


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
            if whole := _WHOLE_CHOICE_UNAVAILABLE.match(line):
                unavailable.add(whole.group("tool"))
                current = None
            elif heading := _ROW_HEADING.match(line):
                current = rows.setdefault(
                    (heading.group("tool"), heading.group("argument"), heading.group("parent")), _Row()
                )
                current.writes = bool(heading.group("rest").strip())
                section = None
            elif line.strip() in ("いまできる:", "いまできない:"):
                section = line.strip()
            elif current is not None and line.strip() == "(なし)":
                pass
            elif current is not None and (quoted := _QUOTED.match(line.strip())) and section is not None:
                if section == "いまできる:":
                    current.available.append(quoted.group("value"))
            else:
                unreadable.append(line)
        return cls(rows, frozenset(unavailable), tuple(unreadable))

    def row(self, tool: str, argument: str, chosen: Sequence[str]) -> _Row | None:
        for parent in (*reversed(chosen), None):
            found = self.rows.get((tool, argument, parent))
            if found is not None:
                return found
        return None

    def details_of(self, tool: str, chosen: Sequence[str]) -> list[str]:
        names = {
            argument[len(_DETAILS) + 1 :]
            for (row_tool, argument, parent) in self.rows
            if row_tool == tool and argument.startswith(f"{_DETAILS}.") and (parent is None or parent in chosen)
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
        if name in _LEFT_UNWRITTEN or name == _DETAILS:
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
        elif name in required or row is not None or rng.random() < _OPTIONAL_PROBABILITY:
            arguments[name] = RANDOM_TEXT
    if _DETAILS in properties:
        details = {}
        for name in table.details_of(tool, chosen):
            row = table.row(tool, f"{_DETAILS}.{name}", chosen)
            if row is not None and row.available:
                details[name] = rng.choice(row.available)
            elif row is not None and row.writes:
                details[name] = RANDOM_TEXT
        if details:
            arguments[_DETAILS] = details
    return arguments, picked


@final
class RandomActionChoosing(ActionChoosingCompletion):
    """同じシードで同じ順に呼ばれれば、同じ行動の並びを返す。並べて呼ぶと順がスレッドの都合で変わる。"""

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
