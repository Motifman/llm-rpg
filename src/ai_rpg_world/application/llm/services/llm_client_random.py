"""提示された tool と引数の候補から、シードに従ってでたらめに行動を選ぶ ILLMClient。

実 run の前に、シナリオの組み合わせの穴を費用をかけずに探すために使う (#1557)。
選べる値はエージェントに見えているものだけにする。ツール定義の enum と、ユーザー
プロンプトの【現在選べる対象引数】の表である。名前を指す引数に候補が無いツールは
選ばない。でたらめでも、世界に実在する行動だけを試すため。
"""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ai_rpg_world.application.llm.ports.llm_client_port import ILLMClient, ToolChoice
from ai_rpg_world.application.llm.services.dynamic_argument_candidates import (
    parse_dynamic_argument_candidate_table,
)
from ai_rpg_world.application.llm.services.llm_client_stub import (
    StubLlmClient,
    _stub_response,
)

RANDOM_FREE_TEXT = "でたらめに選んだ行動"

_OPTIONAL_ARGUMENT_PROBABILITY = 0.5

#: 世界の中のものを指すツールを、待つ・メモ・独り言より多く選ぶ。組み合わせの穴は、ものに触る行動で開くため。
_NAMED_TOOL_WEIGHT = 4


@dataclass(frozen=True)
class _Candidates:
    """候補表を、引数ごとの値と、対象ごとの値に分けて引けるようにしたもの。"""

    by_argument: Mapping[tuple[str, str], tuple[str, ...]]
    by_target: Mapping[tuple[str, str, str], tuple[str, ...]]

    @classmethod
    def from_entries(cls, entries: Sequence[Mapping[str, Any]]) -> _Candidates:
        by_argument: dict[tuple[str, str], tuple[str, ...]] = {}
        by_target: dict[tuple[str, str, str], tuple[str, ...]] = {}
        for entry in entries:
            values = tuple(str(v) for v in entry["values"])
            key = (str(entry["tool"]), str(entry["argument"]))
            target = entry.get("target")
            if target is None:
                by_argument[key] = values
            else:
                by_target[(*key, str(target))] = values
        return cls(by_argument=by_argument, by_target=by_target)

    def targeted(self, tool: str, argument: str) -> dict[str, tuple[str, ...]]:
        return {t: v for (tl, arg, t), v in self.by_target.items() if tl == tool and arg == argument}


def _needs_named_value(name: str) -> bool:
    """世界の中のものを名前か ID で指す引数か。候補が無ければ実在する値を作れない。"""
    return name.endswith(("_label", "_id", "_ids")) or name == "action_name"


def _points_at_something(parameters: Mapping[str, Any]) -> bool:
    return any(_needs_named_value(name) for name in parameters.get("required") or [])


def _last_user_text(messages: Sequence[Mapping[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") == "user":
            return str(message.get("content") or "")
    return ""


class _Infeasible(Exception):
    """このツールは、いま提示されている候補では実在する呼び出しを作れない。"""


def _scalar_value(
    rng: random.Random,
    schema: Mapping[str, Any],
    name: str,
    candidates: tuple[str, ...] | None,
) -> Any:
    if candidates:
        return rng.choice(candidates)
    if _needs_named_value(name):
        raise _Infeasible(name)
    if schema.get("enum"):
        return rng.choice(list(schema["enum"]))
    kind = schema.get("type")
    if kind == "boolean":
        return rng.choice([True, False])
    if kind in ("integer", "number"):
        return 1
    if kind == "string":
        return RANDOM_FREE_TEXT
    raise _Infeasible(name)


def _build_arguments(
    rng: random.Random,
    tool: str,
    parameters: Mapping[str, Any],
    candidates: _Candidates,
) -> dict[str, Any]:
    properties: Mapping[str, Any] = parameters.get("properties") or {}
    required = set(parameters.get("required") or [])
    arguments: dict[str, Any] = {}
    targeted_actions = candidates.targeted(tool, "action_name")
    for name, schema in properties.items():
        own = candidates.by_argument.get((tool, name))
        if name not in required:
            optional_has_choice = bool(own) or bool(schema.get("enum")) or schema.get("type") == "boolean"
            if not optional_has_choice or rng.random() >= _OPTIONAL_ARGUMENT_PROBABILITY:
                continue
        if name == "action_name" and targeted_actions:
            target = arguments.get("target_label")
            if target not in targeted_actions:
                raise _Infeasible(name)
            arguments[name] = rng.choice(targeted_actions[target])
            continue
        if name == "target_label" and targeted_actions and "action_name" in required:
            own = tuple(t for t in (own or ()) if t in targeted_actions) or tuple(targeted_actions)
        if schema.get("type") == "array":
            arguments[name] = _array_value(rng, tool, name, schema, candidates)
            continue
        if schema.get("type") == "object":
            raise _Infeasible(name)
        arguments[name] = _scalar_value(rng, schema, name, own)
    return arguments


def _array_value(
    rng: random.Random,
    tool: str,
    name: str,
    schema: Mapping[str, Any],
    candidates: _Candidates,
) -> list[Any]:
    """1 要素だけの配列を作る。要素が object なら、``name[].field`` の候補で埋める。"""
    items: Mapping[str, Any] = schema.get("items") or {}
    if items.get("type") == "object":
        element: dict[str, Any] = {}
        item_required = set(items.get("required") or [])
        for field, field_schema in (items.get("properties") or {}).items():
            own = candidates.by_argument.get((tool, f"{name}[].{field}"))
            if field not in item_required and not own:
                continue
            element[field] = _scalar_value(rng, field_schema, field, own)
        return [element]
    return [_scalar_value(rng, items, name, candidates.by_argument.get((tool, name)))]


def choose_random_tool_call(
    rng: random.Random,
    messages: Sequence[Mapping[str, Any]],
    tools: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """提示された tool と候補から、実在する呼び出しを 1 つでたらめに作る。作れなければ None。"""
    candidates = _Candidates.from_entries(parse_dynamic_argument_candidate_table(_last_user_text(messages)))
    feasible: list[dict[str, Any]] = []
    weights: list[int] = []
    for tool in tools:
        function = tool.get("function") or {}
        name = str(function.get("name") or "")
        parameters = function.get("parameters") or {}
        try:
            arguments = _build_arguments(rng, name, parameters, candidates)
        except _Infeasible:
            continue
        feasible.append({"name": name, "arguments": arguments})
        weights.append(_NAMED_TOOL_WEIGHT if _points_at_something(parameters) else 1)
    if not feasible:
        return None
    return rng.choices(feasible, weights=weights)[0]


class RandomLlmClient(ILLMClient):
    """呼ばれるたびに、提示された候補から 1 つの行動をでたらめに選ぶ。

    同じシードで同じ順に呼ばれれば、同じ行動の並びを返す。選んだ行動は ``choices`` に残る。
    """

    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)
        self.choices: list[dict[str, Any] | None] = []

    def invoke(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: ToolChoice = "required",
        *,
        metrics_sink: Any | None = None,
        reasoning_effort: str | None = None,
        prompt_capture_context: Any | None = None,
        call_phase: str = "one_step",
        session_id: str | None = None,
    ) -> dict[str, Any] | None:
        tool_call = choose_random_tool_call(self._rng, messages, tools)
        self.choices.append(tool_call)
        StubLlmClient._record_prompt_capture(
            prompt_capture_context,
            request_kwargs={
                "model": "random",
                "messages": messages,
                "tools": tools,
                "tool_choice": tool_choice,
                "max_retries": 0,
            },
            response=_stub_response(tool_call),
            error=None,
            output=tool_call,
            success=tool_call is not None,
            error_code=None if tool_call is not None else "NO_TOOL_CALL",
            call_phase=call_phase,
        )
        return tool_call
