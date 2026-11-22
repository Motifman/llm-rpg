"""LLM を呼ばず、決めておいた答えを順に返す。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from ai_rpg_world.being.application.choose_action import ActionChoosingCompletion, ActionChoosingReply


@dataclass(frozen=True)
class ActionChoosingCall:
    messages: tuple[dict[str, str], ...]
    tools: tuple[dict[str, Any], ...]
    reasoning_off: bool


class ScriptedActionChoosing(ActionChoosingCompletion):
    """答えを使い切ったあとに呼ばれたら ``LookupError`` を投げる。"""

    def __init__(self, replies: Sequence[ActionChoosingReply]) -> None:
        self._replies = list(replies)
        self.calls: list[ActionChoosingCall] = []

    def choose_action(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]], *, reasoning_off: bool
    ) -> ActionChoosingReply:
        self.calls.append(ActionChoosingCall(tuple(messages), tuple(tools), reasoning_off))
        if not self._replies:
            raise LookupError("no scripted reply is left")
        return self._replies.pop(0)


__all__ = ["ActionChoosingCall", "ScriptedActionChoosing"]
