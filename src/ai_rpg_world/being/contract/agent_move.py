"""エージェントの 1 手。

「何をしたか」だけを持つ。結果は経路「自分の行動の結果」の観測として、
``call_id`` で結ばれて届く。
"""

from __future__ import annotations

import math
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Union

from ai_rpg_world.being.contract.errors import (
    ContractViolation,
    require_optional_text,
    require_text,
)

JsonValue = Union[None, bool, int, float, str, tuple["JsonValue", ...], "FrozenJsonObject"]


class FrozenJsonObject(Mapping[str, JsonValue]):
    """JSON の値だけを持つ、書き換えられない対応表。

    ツールの引数はツールごとに形が違うので欄を契約で決められない。代わりに値を
    JSON に限り、環境のオブジェクトや ID の型が紛れ込まないようにする。
    """

    __slots__ = ("_items",)

    def __init__(self, items: Mapping[str, object]) -> None:
        if not isinstance(items, Mapping):
            raise ContractViolation("arguments must be Mapping")
        for name in items:
            require_text(name, "argument name")
        self._items: tuple[tuple[str, JsonValue], ...] = tuple(
            (name, freeze_json(value)) for name, value in items.items()
        )

    def __getitem__(self, key: str) -> JsonValue:
        for name, value in self._items:
            if name == key:
                return value
        raise KeyError(key)

    def __iter__(self) -> Iterator[str]:
        return (name for name, _ in self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __hash__(self) -> int:
        return hash(frozenset(self._items))

    def __repr__(self) -> str:
        return f"FrozenJsonObject({dict(self._items)!r})"


def freeze_json(value: object) -> JsonValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractViolation("argument values must be finite numbers")
        return value
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(v) for v in value)
    if isinstance(value, Mapping):
        return value if isinstance(value, FrozenJsonObject) else FrozenJsonObject(value)
    raise ContractViolation(f"argument values must be JSON values, got {type(value).__name__}")


@dataclass(frozen=True, kw_only=True)
class AgentMove:
    call_id: str
    tool_name: str
    arguments: Mapping[str, JsonValue]
    expectation: str | None = None
    inner_thought: str | None = None
    goal_update: str | None = None

    def __post_init__(self) -> None:
        require_text(self.call_id, "call_id")
        require_text(self.tool_name, "tool_name")
        object.__setattr__(self, "arguments", FrozenJsonObject(self.arguments))
        require_optional_text(self.expectation, "expectation")
        require_optional_text(self.inner_thought, "inner_thought")
        require_optional_text(self.goal_update, "goal_update")
