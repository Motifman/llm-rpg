from __future__ import annotations

import threading
from typing import Any, final

from ai_rpg_world.being.application.choose_action import (
    ActionChoosingCompletion,
    ActionChoosingReply,
    ToolCallReply,
)

_SPEAK = "speak"


@final
class MurmuringActionChoosing(ActionChoosingCompletion):
    """実 LLM を呼ばずに配線を確かめるスタブ。話せるときは、ふつうの声で一言つぶやく。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls = 0

    def choose_action(
        self, messages: list[dict[str, str]], tools: list[dict[str, Any]], *, reasoning_off: bool
    ) -> ActionChoosingReply:
        with self._lock:
            self._calls += 1
            call_id = f"murmur_{self._calls}"
        if not any(tool.get("function", {}).get("name") == _SPEAK for tool in tools):
            return ActionChoosingReply(tool_call=None)
        return ActionChoosingReply(
            tool_call=ToolCallReply(
                tool_name=_SPEAK, arguments={"reach": "ふつうの声で話す", "content": "ふむ"}, call_id=call_id
            )
        )
