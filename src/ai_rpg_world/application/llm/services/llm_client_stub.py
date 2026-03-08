"""
ILLMClient のスタブ実装（テスト・開発用）。

実際の LLM API 呼び出しはインフラ層で ILLMClient を実装して差し替える。
"""

from typing import Any, Dict, List, Optional, Union

from ai_rpg_world.application.llm.contracts.interfaces import ILLMClient


class StubLlmClient(ILLMClient):
    """
    テスト用: 呼び出しごとに返す tool_call を設定できる。
    exception_to_raise を設定すると invoke 時にその例外を投げる。
    """

    def __init__(
        self,
        tool_call_to_return: Optional[Dict[str, Any]] = None,
        exception_to_raise: Optional[Exception] = None,
    ) -> None:
        """
        tool_call_to_return: invoke が返す値。例: {"name": "world_no_op", "arguments": {}}
        None のときは invoke は None を返す。
        exception_to_raise: 設定時は invoke でその例外を投げる（tool_call_to_return より優先）。
        """
        self._tool_call_to_return = tool_call_to_return
        self._exception_to_raise = exception_to_raise

    def set_tool_call_to_return(self, tool_call: Optional[Dict[str, Any]]) -> None:
        """次回の invoke で返す tool_call を設定する。"""
        self._tool_call_to_return = tool_call

    def set_exception_to_raise(self, exc: Optional[Exception]) -> None:
        """次回の invoke で投げる例外を設定する。"""
        self._exception_to_raise = exc

    def invoke(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "required",
    ) -> Optional[Dict[str, Any]]:
        if self._exception_to_raise is not None:
            raise self._exception_to_raise
        return self._tool_call_to_return
