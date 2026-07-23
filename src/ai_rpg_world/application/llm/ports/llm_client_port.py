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


ToolChoice = str | Dict[str, Any]


class ILLMClient(ABC):
    """LLM 呼び出しクライアント。"""

    @abstractmethod
    def invoke(
        self,
        messages: List[Dict[str, str]],
        tools: List[Dict[str, Any]],
        tool_choice: ToolChoice = "required",
        *,
        metrics_sink: Optional[Any] = None,
        reasoning_effort: Optional[str] = None,
        prompt_capture_context: Optional[Any] = None,
        call_phase: str = "one_step",
    ) -> Optional[Dict[str, Any]]:
        """
        LLM を呼び出し、選択された tool_call を返す。
        返り値例: {"name": "move_to_destination", "arguments": "{...}"}

        ``metrics_sink`` (``LlmCallMetricsSink``) が渡されたら、呼び出し完了時に
        ``LlmCallMetrics`` で記録する (実装側の任意)。実 LLM クライアントは
        wall_latency + token usage を埋め、stub 系は best-effort で実装する。

        ``reasoning_effort`` が渡されたら、その 1 呼び出しだけ reasoning (熟考) の
        予算段階を上書きする (案A: band-gated thinking)。``None`` なら既定のまま。
        stub 系は無視してよい。

        ``prompt_capture_context`` が渡されたら、実装側は実際に外部 LLM 境界へ渡した
        request と response を prompt dataset sink へ保存する。既定 ``None`` なら
        完全に無効。

        ``call_phase`` は prompt dataset / metrics / trace 上の区別用。通常の
        1段階ターンは ``one_step``、reason-first 2段階ターンでは
        ``assess_phase`` / ``action_phase`` を呼び出し側が指定する。
        """
        pass


__all__ = ["ILLMClient", "ToolChoice"]
