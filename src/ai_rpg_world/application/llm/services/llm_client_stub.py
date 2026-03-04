"""
ILLMClient のスタブ実装（テスト・開発用）。

実際の LLM API 呼び出しはインフラ層で ILLMClient を実装して差し替える。
"""

from typing import Any, Dict, List, Optional

from ai_rpg_world.application.llm.contracts.interfaces import ILLMClient


class StubLlmClient(ILLMClient):
    """
    テスト用: 呼び出しごとに返す tool_call を設定できる。
    """

    def __init__(
        self,
        tool_call_to_return: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        tool_call_to_return: invoke が返す値。例: {"name": "world_no_op", "arguments": {}}
        None のときは invoke は None を返す。
        """
        self._tool_call_to_return = tool_call_to_return

    def set_tool_call_to_return(self, tool_call: Optional[Dict[str, Any]]) -> None:
        """次回の invoke で返す tool_call を設定する。"""
        self._tool_call_to_return = tool_call

    def invoke(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "required",
    ) -> Optional[Dict[str, Any]]:
        return self._tool_call_to_return
