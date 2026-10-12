"""AuxLlmCallTraceSink が記憶の部品と Jev の呼び出しを aux_llm_call として trace に残し、残せなかったことも trace に残すことを保証する (#1617)。"""

from __future__ import annotations

from typing import Any

from ai_rpg_world.application.llm.contracts.aux_llm_call import (
    AuxLlmCall,
    AuxLlmComponent,
)
from ai_rpg_world.application.llm.services.aux_llm_call_trace_sink import (
    AuxLlmCallTraceSink,
)
from ai_rpg_world.application.trace import TraceEventKind


class _Recorder:
    def __init__(self, *, fail_on: frozenset[str] = frozenset()) -> None:
        self.events: list[tuple[str, int | None, int | None, dict[str, Any]]] = []
        self._fail_on = fail_on

    def record(self, kind: str, *, tick: int | None = None, player_id: int | None = None, **payload: Any) -> None:
        if kind in self._fail_on:
            raise RuntimeError(f"cannot record {kind}")
        self.events.append((kind, tick, player_id, payload))


def _sink(recorder: Any, tick: int = 7) -> AuxLlmCallTraceSink:
    return AuxLlmCallTraceSink(
        trace_recorder_provider=lambda: recorder,
        current_tick_provider=lambda: tick,
    )


_SUMMARY_CALL = AuxLlmCall(
    component=AuxLlmComponent.SHORT_TERM_SUMMARY,
    model="openai/gpt-5-mini",
    wall_latency_ms=1234,
    success=True,
    prompt_tokens=500,
    completion_tokens=80,
    cached_tokens=256,
    cost_usd=0.0007,
)


class TestCallsBecomeAuxLlmCallEvents:
    """1 回の呼び出しが、行動の llm_call とは別の aux_llm_call 1 件になることを保証する。"""

    def test_call_is_written_as_aux_llm_call_with_all_measured_values(self) -> None:
        """記録は aux_llm_call の kind で、現在の tick と、部品名・モデル・待ち時間・トークン・費用・成否を payload に持つ。"""
        recorder = _Recorder()

        _sink(recorder, tick=7).record(_SUMMARY_CALL)

        assert len(recorder.events) == 1
        kind, tick, player_id, payload = recorder.events[0]
        assert kind == TraceEventKind.AUX_LLM_CALL == "aux_llm_call"
        assert tick == 7
        assert player_id is None
        assert payload == {
            "component": "short_term_summary",
            "model": "openai/gpt-5-mini",
            "wall_latency_ms": 1234,
            "success": True,
            "error_code": None,
            "prompt_tokens": 500,
            "completion_tokens": 80,
            "cached_tokens": 256,
            "cost_usd": 0.0007,
            "question_names": [],
        }

    def test_unavailable_cost_is_written_as_null(self) -> None:
        """費用が取れなかった呼び出しは cost_usd が None のまま残る (0.0 に埋めない)。"""
        recorder = _Recorder()
        call = AuxLlmCall(
            component=AuxLlmComponent.TYPED_JUDGMENT,
            model="typesafe/jev-1.13",
            wall_latency_ms=900,
            success=True,
            question_names=("goal_achieved",),
        )

        _sink(recorder).record(call)

        payload = recorder.events[0][3]
        assert payload["cost_usd"] is None
        assert payload["prompt_tokens"] is None
        assert payload["question_names"] == ["goal_achieved"]


class TestRecordingFailuresAreVisible:
    """trace へ書けなかったことが trace に残り、run は止まらないことを保証する。"""

    def test_failed_write_leaves_record_failed_event_with_component(self) -> None:
        """aux_llm_call の書き込みが例外を投げると、部品名と例外の型を持つ aux_llm_call_record_failed を 1 件残し、例外は外へ出さない。"""
        recorder = _Recorder(fail_on=frozenset({TraceEventKind.AUX_LLM_CALL}))

        _sink(recorder, tick=3).record(_SUMMARY_CALL)

        assert recorder.events == [
            (
                TraceEventKind.AUX_LLM_CALL_RECORD_FAILED,
                3,
                None,
                {"component": "short_term_summary", "error_type": "RuntimeError"},
            )
        ]

    def test_both_writes_failing_does_not_raise(self) -> None:
        """失敗の記録まで書けなくても、例外は外へ出さない。"""
        recorder = _Recorder(
            fail_on=frozenset(
                {TraceEventKind.AUX_LLM_CALL, TraceEventKind.AUX_LLM_CALL_RECORD_FAILED}
            )
        )

        _sink(recorder).record(_SUMMARY_CALL)

        assert recorder.events == []

    def test_tick_provider_failure_still_writes_the_call(self) -> None:
        """現在の tick が取れなくても、tick=None で呼び出しを残す。"""
        recorder = _Recorder()

        def _broken_tick() -> int:
            raise RuntimeError("no tick yet")

        AuxLlmCallTraceSink(
            trace_recorder_provider=lambda: recorder,
            current_tick_provider=_broken_tick,
        ).record(_SUMMARY_CALL)

        assert recorder.events[0][0] == TraceEventKind.AUX_LLM_CALL
        assert recorder.events[0][1] is None

    def test_no_recorder_yet_does_not_raise(self) -> None:
        """trace の recorder がまだ差し込まれていないとき、何も書かず例外も出さない。"""
        _sink(None).record(_SUMMARY_CALL)
