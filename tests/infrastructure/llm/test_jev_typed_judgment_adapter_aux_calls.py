"""Jev アダプタが、Decisions endpoint への 1 回ごとに回数・待ち時間・問いの名前を残し、費用が取れないことを None で示すことを保証する (#1617)。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from ai_rpg_world.application.llm.contracts.aux_llm_call import (
    AuxLlmCall,
    AuxLlmComponent,
)
from ai_rpg_world.application.llm.ports.typed_judgment_port import (
    NoulQuestion,
    TypedJudgmentUnavailableException,
)
from ai_rpg_world.infrastructure.llm.jev_typed_judgment_adapter import (
    JevTypedJudgmentAdapter,
)

_QUESTIONS = {
    "goal_achieved": NoulQuestion(instructions="目的は果たされたか"),
    "memo_0": NoulQuestion(instructions="メモは済んだか"),
}


class _Sink:
    def __init__(self) -> None:
        self.calls: list[AuxLlmCall] = []

    def record(self, call: AuxLlmCall) -> None:
        self.calls.append(call)


class _BrokenSink:
    def record(self, call: AuxLlmCall) -> None:
        raise RuntimeError("sink is broken")


def _adapter(handler: Callable[[httpx.Request], httpx.Response], sink: Any) -> JevTypedJudgmentAdapter:
    return JevTypedJudgmentAdapter(
        api_key="sk-or-v1-test",
        endpoint="https://openrouter.ai/api/alpha/decisions",
        model="typesafe/jev-1.13",
        timeout_seconds=5.0,
        rate_limit_retry_attempts=0,
        rate_limit_retry_base_sleep=0.0,
        sleep=lambda _seconds: None,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        aux_call_sink=sink,
    )


def _answers(extra: dict[str, Any] | None = None) -> Callable[[httpx.Request], httpx.Response]:
    body: dict[str, Any] = {
        "answers": {
            "goal_achieved": {"type": "noul", "noul": 0.9},
            "memo_0": {"type": "noul", "noul": 0.1},
        }
    }
    body.update(extra or {})
    return lambda _request: httpx.Response(200, json=body)


class TestEachDecisionCallLeavesOneRecord:
    """Decisions endpoint への 1 回が 1 件の記録になることを保証する。"""

    def test_successful_call_records_count_latency_and_question_names(self) -> None:
        """成功した 1 回は、部品名 typed_judgment・モデル名・待ち時間・問いの名前を 1 件残す。"""
        sink = _Sink()

        _adapter(_answers(), sink).judge("state", _QUESTIONS)

        assert len(sink.calls) == 1
        call = sink.calls[0]
        assert call.component is AuxLlmComponent.TYPED_JUDGMENT
        assert call.model == "typesafe/jev-1.13"
        assert call.success is True
        assert call.question_names == ("goal_achieved", "memo_0")
        assert call.wall_latency_ms >= 0

    def test_response_without_usage_records_cost_and_tokens_as_none(self) -> None:
        """応答に usage が無いとき、費用とトークン数は 0 ではなく None で残る (取れないと分かる形)。"""
        sink = _Sink()

        _adapter(_answers(), sink).judge("state", _QUESTIONS)

        call = sink.calls[0]
        assert call.cost_usd is None
        assert call.prompt_tokens is None
        assert call.completion_tokens is None

    def test_response_with_usage_cost_records_that_cost(self) -> None:
        """応答の usage に cost と tokens があれば、その値を残す。"""
        sink = _Sink()

        _adapter(
            _answers({"usage": {"cost": 0.0021, "prompt_tokens": 300, "completion_tokens": 7}}),
            sink,
        ).judge("state", _QUESTIONS)

        call = sink.calls[0]
        assert call.cost_usd == pytest.approx(0.0021)
        assert (call.prompt_tokens, call.completion_tokens) == (300, 7)

    def test_empty_questions_send_nothing_and_record_nothing(self) -> None:
        """問いが 0 件なら送らず、記録も残さない (呼んでいない回を数えない)。"""
        sink = _Sink()

        _adapter(_answers(), sink).judge("state", {})

        assert sink.calls == []


class TestFailedDecisionCallsAreRecordedToo:
    """失敗した 1 回も記録し、呼び出し元への例外は変えないことを保証する。"""

    def test_http_error_records_failure_and_still_raises(self) -> None:
        """HTTP 500 のとき、success=False と error_code を 1 件残してから TypedJudgmentUnavailableException を投げる。"""
        sink = _Sink()
        adapter = _adapter(lambda _request: httpx.Response(500, json={}), sink)

        with pytest.raises(TypedJudgmentUnavailableException) as exc_info:
            adapter.judge("state", _QUESTIONS)

        assert len(sink.calls) == 1
        call = sink.calls[0]
        assert call.success is False
        assert call.error_code == exc_info.value.error_code == "TYPED_JUDGMENT_HTTP_ERROR"

    def test_schema_mismatch_records_failure(self) -> None:
        """答えが欠けた応答は、success=False と TYPED_JUDGMENT_ANSWER_MISSING を残す (課金された 1 回として数える)。"""
        sink = _Sink()
        adapter = _adapter(lambda _request: httpx.Response(200, json={"answers": {}}), sink)

        with pytest.raises(TypedJudgmentUnavailableException):
            adapter.judge("state", _QUESTIONS)

        assert sink.calls[0].error_code == "TYPED_JUDGMENT_ANSWER_MISSING"


class TestRecordingFailureDoesNotStopTheJudgment:
    """記録の失敗が判断を倒さないことを保証する。"""

    def test_broken_sink_still_returns_answers(self) -> None:
        """sink.record が例外を投げても、judge は答えを返す。"""
        results = _adapter(_answers(), _BrokenSink()).judge("state", _QUESTIONS)

        assert set(results) == {"goal_achieved", "memo_0"}
