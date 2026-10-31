"""考えが出力の上限で切れて行動を返せなかった呼び出しを、考えを止めて 1 回だけ呼び直す (#1924、design_decisions D1924)。

DeepSeek は考えだけに上限を掛けられず、考えが出力の上限を使い切ると、ツールを呼ぶ前に打ち切られる。同じメッセージを
考えを止めて送り直せば、プレフィックスのキャッシュを崩さずに行動を返させられる。途中までの考えは添えない。切れた考えは
同じ所を回っていることが多く、添えると迷いを持ち込むおそれがあるため。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ai_rpg_world.application.trace import TraceEventKind
from ai_rpg_world.domain.player.value_object.player_id import PlayerId

TRUNCATED_FINISH_REASON = "length"
RETRY_REASONING_EFFORT = "none"
_REASONING_OFF = frozenset({"", "none"})
_logger = logging.getLogger(__name__)


class CallOutcomeWatch:
    """1 回の呼び出しの計測を受け、打ち切りの理由と考えの段階を覚えてから、trace の記録係へ渡す。

    trace の記録係が無いとき (``inner`` が None) も覚える。呼び直すかの判断を trace の有無に左右させないため。
    """

    def __init__(self, inner: Any | None) -> None:
        self._inner = inner
        self.finish_reason: str | None = None
        self.reasoning_effort: str | None = None

    def record(self, metrics: Any) -> None:
        self.finish_reason = getattr(metrics, "finish_reason", None)
        self.reasoning_effort = getattr(metrics, "reasoning_effort", None)
        if self._inner is not None:
            self._inner.record(metrics)

    @property
    def cut_off_while_reasoning(self) -> bool:
        """考えを有効にした呼び出しが、出力の上限で打ち切られた。考えを止めない呼び出しは、呼び直しても同じになる。"""
        return self.finish_reason == TRUNCATED_FINISH_REASON and (self.reasoning_effort or "") not in _REASONING_OFF


def _record_retry(wiring: Any, player_id: PlayerId, **payload: Any) -> None:
    trace_recorder = getattr(wiring.runtime, "trace_recorder", None)
    if trace_recorder is None:
        return
    try:
        tick: int | None = int(wiring.runtime.current_tick())
    except Exception:
        tick = None
    try:
        trace_recorder.record(
            TraceEventKind.LLM_OUTPUT_TRUNCATED_RETRY, tick=tick, player_id=int(player_id.value), **payload
        )
    except Exception:
        _logger.exception("trace_recorder.record(%s) failed", TraceEventKind.LLM_OUTPUT_TRUNCATED_RETRY)


class TruncatedOutputRetryAllowance:
    """1 つの段 (1 段の呼び出し、評価の段、行動の段) で、打ち切られたときに呼び直してよい残りの回数。1 回だけ。

    評価の段は、評価が成立しないと 2 周目を呼ぶ。その周に別の許しを渡すと、1 つの段で 2 回呼び直してしまうので、
    段ごとに 1 つ作って周をまたいで渡す。
    """

    def __init__(self) -> None:
        self._used = False

    @property
    def available(self) -> bool:
        return not self._used

    def use(self) -> None:
        self._used = True


InvokeOnce = Callable[[int, "str | None", "str | None", CallOutcomeWatch], "dict[str, Any] | None"]


def invoke_retrying_truncated_output(
    invoke: InvokeOnce,
    *,
    wiring: Any,
    player_id: PlayerId,
    phase: str,
    metrics_sink: Any | None,
    attempt_index: int,
    parent_attempt_id: str | None,
    last_llm_call_id: Callable[[], str | None],
    allowance: TruncatedOutputRetryAllowance,
) -> dict[str, Any] | None:
    """``invoke(attempt_index, parent_attempt_id, reasoning_effort, watch)`` を呼び、打ち切られていれば 1 回だけ呼び直す。

    呼び直すのは、``allowance`` が残っていて、行動 (ツールの呼び出し) が返らず、考えを有効にした呼び出しが出力の
    上限で打ち切られたときだけ。呼び直す前に ``allowance`` を使う。呼び直しも行動を返さなければ、そのまま None を返す。
    呼び直しの例外は呼び出し元へ投げる。
    """
    watch = CallOutcomeWatch(metrics_sink)
    tool_call = invoke(attempt_index, parent_attempt_id, None, watch)
    if tool_call is not None or not allowance.available or not watch.cut_off_while_reasoning:
        return tool_call
    allowance.use()
    truncated_llm_call_id = last_llm_call_id()
    retry_watch = CallOutcomeWatch(metrics_sink)
    trace: dict[str, Any] = {
        "phase": phase,
        "truncated_llm_call_id": truncated_llm_call_id,
        "reasoning_effort": watch.reasoning_effort,
    }
    try:
        tool_call = invoke(attempt_index + 1, truncated_llm_call_id, RETRY_REASONING_EFFORT, retry_watch)
    except Exception as exc:
        _record_retry(
            wiring,
            player_id,
            **trace,
            retry_llm_call_id=last_llm_call_id(),
            outcome="invoke_exception",
            error_type=type(exc).__name__,
        )
        raise
    _record_retry(
        wiring,
        player_id,
        **trace,
        retry_llm_call_id=last_llm_call_id(),
        outcome="tool_call" if tool_call is not None else "no_tool_call",
        returned_tool=str(tool_call.get("name", "")) if isinstance(tool_call, dict) else None,
        retry_finish_reason=retry_watch.finish_reason,
    )
    return tool_call


__all__ = ["CallOutcomeWatch", "TruncatedOutputRetryAllowance", "invoke_retrying_truncated_output"]
