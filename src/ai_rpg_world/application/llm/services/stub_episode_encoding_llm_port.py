"""IEpisodeEncodingLlmPort のテスト用スタブ。"""

from typing import Any, Dict, Optional

from ai_rpg_world.application.llm.contracts.interfaces import IEpisodeEncodingLlmPort


class StubEpisodeEncodingLlmPort(IEpisodeEncodingLlmPort):
    """固定文字列を返す。JSON テストなら呼び出し側で有効な JSON を渡す。"""

    def __init__(self, response_text: str = "{}") -> None:
        if not isinstance(response_text, str):
            raise TypeError("response_text must be str")
        self._response_text = response_text
        self.calls: list[tuple[str, str, Optional[Dict[str, Any]]]] = []

    def set_response_text(self, text: str) -> None:
        if not isinstance(text, str):
            raise TypeError("text must be str")
        self._response_text = text

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not isinstance(system_prompt, str):
            raise TypeError("system_prompt must be str")
        if not isinstance(user_prompt, str):
            raise TypeError("user_prompt must be str")
        self.calls.append((system_prompt, user_prompt, response_format))
        return self._response_text
