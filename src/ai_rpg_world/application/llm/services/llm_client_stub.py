"""
ILLMClient のスタブ実装（テスト・開発用）。

実際の LLM API 呼び出しはインフラ層で ILLMClient を実装して差し替える。
"""

from typing import Any, Dict, List, Optional

from ai_rpg_world.application.llm.ports.llm_client_port import ILLMClient, ToolChoice


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
        tool_choice: ToolChoice = "required",
        *,
        metrics_sink: Optional[Any] = None,
        reasoning_effort: Optional[str] = None,
        prompt_capture_context: Optional[Any] = None,
        call_phase: str = "one_step",
    ) -> Optional[Dict[str, Any]]:
        # stub は metrics_sink / reasoning_effort を受け取るが何もしない (テスト互換、
        # 実 client が出す計測値や reasoning 制御を fake する必要がない場合の default)。
        request_kwargs = {
            "model": "stub",
            "messages": messages,
            "tools": tools,
            "tool_choice": tool_choice,
            "max_retries": 0,
        }
        if self._exception_to_raise is not None:
            self._record_prompt_capture(
                prompt_capture_context,
                request_kwargs=request_kwargs,
                response=None,
                error=self._exception_to_raise,
                output=None,
                success=False,
                error_code=getattr(
                    self._exception_to_raise, "error_code", "STUB_LLM_EXCEPTION"
                ),
                call_phase=call_phase,
            )
            raise self._exception_to_raise
        self._record_prompt_capture(
            prompt_capture_context,
            request_kwargs=request_kwargs,
            response=_stub_response(self._tool_call_to_return),
            error=None,
            output=self._tool_call_to_return,
            success=self._tool_call_to_return is not None,
            error_code=None if self._tool_call_to_return is not None else "NO_TOOL_CALL",
            call_phase=call_phase,
        )
        return self._tool_call_to_return

    @staticmethod
    def _record_prompt_capture(
        prompt_capture_context: Optional[Any],
        *,
        request_kwargs: Dict[str, Any],
        response: Any,
        error: Optional[BaseException],
        output: Optional[Dict[str, Any]],
        success: bool,
        error_code: Optional[str],
        call_phase: str,
    ) -> None:
        if prompt_capture_context is None:
            return
        prompt_capture_context.sink.record_call(
            context=prompt_capture_context.context,
            request_kwargs=request_kwargs,
            response=response,
            error=error,
            output=output,
            metrics={
                "wall_latency_ms": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "cached_tokens": 0,
                "reasoning_tokens": 0,
                "cost_usd": 0.0,
                "success": success,
                "error_code": error_code,
                "phase": call_phase,
            },
        )


def _stub_response(tool_call: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """stub の tool_call から replay 監査用の最小 response を作る。"""

    tool_calls = []
    if tool_call is not None:
        tool_calls.append(
            {
                "id": "stub-call",
                "type": "function",
                "function": {
                    "name": tool_call.get("name"),
                    "arguments": tool_call.get("arguments"),
                },
            }
        )
    return {
        "id": "stub-response",
        "object": "chat.completion",
        "model": "stub",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": tool_calls,
                },
                "finish_reason": "tool_calls" if tool_calls else "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }
