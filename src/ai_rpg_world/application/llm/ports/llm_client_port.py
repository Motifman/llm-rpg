"""ILLMClient — tool-use 付き LLM 呼び出しの抽象 Port。

Issue #470 Phase 1 cleanup A3: 旧 ``contracts/interfaces.py`` から本ファイルに
分離。``ports/`` 配下の他の completion port (``*CompletionPort``) と同じく
**外部 LLM API への口** という責務。

他 port との違い: ``I*CompletionPort`` は「無ツール JSON 完了」(messages → dict)
専用だが、本 port は **tool_use 付き** で tool_call を返す。LLM agent ターン
本体 (= prompt builder → ILLMClient → tool_executor) で使われる中核 port。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class ILLMClient(ABC):
    """LLM 呼び出しクライアント。"""

    @abstractmethod
    def invoke(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "required",
        *,
        metrics_sink: Optional[Any] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        LLM を呼び出し、選択された tool_call を返す。
        返り値例: {"name": "move_to_destination", "arguments": "{...}"}

        ``metrics_sink`` (``LlmCallMetricsSink``) が渡されたら、呼び出し完了時に
        ``LlmCallMetrics`` で記録する (実装側の任意)。実 LLM クライアントは
        wall_latency + token usage を埋め、stub 系は best-effort で実装する。
        """
        pass


__all__ = ["ILLMClient"]
