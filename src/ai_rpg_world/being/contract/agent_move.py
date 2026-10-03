"""エージェントの 1 手。

「何をしたか」だけを持つ。結果は経路「自分の行動の結果」の観測として、
``call_id`` で結ばれて届く。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from ai_rpg_world.being.contract.errors import (
    ContractViolation,
    require_optional_text,
    require_text,
)


@dataclass(frozen=True, kw_only=True)
class AgentMove:
    call_id: str
    tool_name: str
    arguments: Mapping[str, Any]
    expectation: str | None = None
    inner_thought: str | None = None
    goal_update: str | None = None

    def __post_init__(self) -> None:
        require_text(self.call_id, "call_id")
        require_text(self.tool_name, "tool_name")
        if not isinstance(self.arguments, Mapping):
            raise ContractViolation("arguments must be Mapping")
        for name in self.arguments:
            require_text(name, "argument name")
        object.__setattr__(self, "arguments", MappingProxyType(dict(self.arguments)))
        require_optional_text(self.expectation, "expectation")
        require_optional_text(self.inner_thought, "inner_thought")
        require_optional_text(self.goal_update, "goal_update")
