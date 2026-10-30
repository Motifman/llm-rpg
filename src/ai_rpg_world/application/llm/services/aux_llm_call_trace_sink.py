"""記憶の部品と Jev の LLM 呼び出しを trace に流す sink (#1617)。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from ai_rpg_world.application.llm.contracts.aux_llm_call import AuxLlmCall
from ai_rpg_world.application.trace import TraceEventKind

logger = logging.getLogger(__name__)


class AuxLlmCallTraceSink:
    """recorder と tick は呼ばれた時点で引く。

    記憶の部品は runtime より先に組まれ、recorder は run の開始時に差し込まれる。
    主観の書き込みは別スレッドで tick を跨いで終わる。
    """

    def __init__(
        self,
        *,
        trace_recorder_provider: Callable[[], Any],
        current_tick_provider: Callable[[], int],
    ) -> None:
        self._trace_recorder_provider = trace_recorder_provider
        self._current_tick_provider = current_tick_provider

    def record(self, call: AuxLlmCall) -> None:
        try:
            recorder = self._trace_recorder_provider()
        except Exception:
            logger.exception("trace recorder provider failed for aux_llm_call")
            return
        if recorder is None:
            return
        try:
            tick: int | None = int(self._current_tick_provider())
        except Exception:
            tick = None
        component = call.component.value
        try:
            recorder.record(
                TraceEventKind.AUX_LLM_CALL,
                tick=tick,
                player_id=None,
                component=component,
                model=call.model,
                wall_latency_ms=call.wall_latency_ms,
                success=call.success,
                error_code=call.error_code,
                prompt_tokens=call.prompt_tokens,
                completion_tokens=call.completion_tokens,
                cached_tokens=call.cached_tokens,
                cost_usd=call.cost_usd,
                question_names=list(call.question_names),
            )
        except Exception as exc:
            logger.exception("trace_recorder.record(aux_llm_call) failed")
            try:
                recorder.record(
                    TraceEventKind.AUX_LLM_CALL_RECORD_FAILED,
                    tick=tick,
                    player_id=None,
                    component=component,
                    error_type=type(exc).__name__,
                )
            except Exception:
                logger.exception("trace_recorder.record(aux_llm_call_record_failed) failed")


__all__ = ["AuxLlmCallTraceSink"]
