"""IMemoryReflectionLlmPort のテスト用スタブ。"""

from typing import Any, Dict, Optional

from ai_rpg_world.application.llm.contracts.interfaces import IMemoryReflectionLlmPort


class StubMemoryReflectionLlmPort(IMemoryReflectionLlmPort):
    def __init__(self, response_text: str) -> None:
        if not isinstance(response_text, str):
            raise TypeError("response_text must be str")
        self._response_text = response_text
        self.calls: list[tuple[str, str, Optional[Dict[str, Any]]]] = []

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        self.calls.append((system_prompt, user_prompt, response_format))
        return self._response_text
