"""LiteLLMClient が、記憶の部品から呼ばれた LLM の 1 回ごとに、部品名・トークン・費用・待ち時間を残すことを保証する (#1617)。"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from ai_rpg_world.application.llm.contracts.aux_llm_call import (
    AuxLlmCall,
    AuxLlmComponent,
)
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient

_LITELLM = "ai_rpg_world.infrastructure.llm.litellm_client.litellm"


@pytest.fixture(autouse=True)
def isolate_litellm_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.delenv("OPENROUTER_PROVIDER", raising=False)
    monkeypatch.delenv("OPENROUTER_QUANTIZATION", raising=False)
    monkeypatch.delenv("OPENROUTER_REQUIRE_PARAMS", raising=False)
    monkeypatch.delenv("LLM_REASONING_EFFORT", raising=False)
    monkeypatch.setattr(
        "ai_rpg_world.infrastructure.llm.litellm_client._load_dotenv_if_available",
        lambda: None,
    )


class _Sink:
    def __init__(self) -> None:
        self.calls: list[AuxLlmCall] = []

    def record(self, call: AuxLlmCall) -> None:
        self.calls.append(call)


class _BrokenSink:
    def record(self, call: AuxLlmCall) -> None:
        raise RuntimeError("sink is broken")


def _response(content: str, *, usage: Any) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=usage,
    )


def _usage(*, prompt: int, completion: int, cached: int, cost: float | None) -> SimpleNamespace:
    fields: dict[str, Any] = {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "prompt_tokens_details": SimpleNamespace(cached_tokens=cached),
    }
    if cost is not None:
        fields["cost"] = cost
    return SimpleNamespace(**fields)


def _client(sink: Any) -> LiteLLMClient:
    return LiteLLMClient(model="openai/gpt-5-mini", api_key="sk-dummy", aux_call_sink=sink)


_METHOD_TO_COMPONENT = [
    ("complete_episode_subjective_json", AuxLlmComponent.EPISODE_SUBJECTIVE),
    ("complete_semantic_gist_json", AuxLlmComponent.SEMANTIC_GIST),
    ("complete_belief_consolidation_json", AuxLlmComponent.BELIEF_CONSOLIDATION),
    ("complete_short_term_summary_json", AuxLlmComponent.SHORT_TERM_SUMMARY),
    ("complete_short_term_long_summary_json", AuxLlmComponent.SHORT_TERM_LONG_SUMMARY),
    ("complete_episode_writing_json", AuxLlmComponent.EPISODE_WRITING),
]


class TestEachComponentLeavesOneRecord:
    """部品ごとの入口が、自分の部品名で 1 件ずつ記録を残すことを保証する。"""

    @pytest.mark.parametrize(("method", "component"), _METHOD_TO_COMPONENT)
    def test_successful_call_records_component_tokens_cost_and_latency(
        self, method: str, component: AuxLlmComponent
    ) -> None:
        """成功した呼び出しは、その入口の部品名と、応答のトークン数・費用・待ち時間・モデル名を 1 件残す。"""
        sink = _Sink()
        client = _client(sink)
        with patch(_LITELLM) as m_litellm:
            m_litellm.completion.return_value = _response(
                '{"ok": true}',
                usage=_usage(prompt=120, completion=30, cached=64, cost=0.00042),
            )
            result = getattr(client, method)([{"role": "user", "content": "x"}])

        assert result == {"ok": True}
        assert len(sink.calls) == 1
        call = sink.calls[0]
        assert call.component is component
        assert call.model == "openai/gpt-5-mini"
        assert call.success is True
        assert call.error_code is None
        assert (call.prompt_tokens, call.completion_tokens, call.cached_tokens) == (120, 30, 64)
        assert call.cost_usd == pytest.approx(0.00042)
        assert call.wall_latency_ms >= 0

    def test_response_without_cost_records_cost_as_none_not_zero(self) -> None:
        """応答の usage に cost が無いとき、費用は 0 ではなく None で残る (直結 / vLLM で無料と読ませない)。"""
        sink = _Sink()
        client = _client(sink)
        with patch(_LITELLM) as m_litellm:
            m_litellm.completion.return_value = _response(
                '{"ok": true}', usage=_usage(prompt=10, completion=5, cached=0, cost=None)
            )
            client.complete_short_term_summary_json([{"role": "user", "content": "x"}])

        assert sink.calls[0].cost_usd is None


    def test_response_without_usage_records_tokens_as_none_not_zero(self) -> None:
        """応答に usage が無いとき、トークン数は 0 ではなく None で残る (usage を返さない provider で 0 トークンと読ませない)。"""
        sink = _Sink()
        client = _client(sink)
        with patch(_LITELLM) as m_litellm:
            m_litellm.completion.return_value = _response('{"ok": true}', usage=None)
            client.complete_short_term_summary_json([{"role": "user", "content": "x"}])

        call = sink.calls[0]
        assert (call.prompt_tokens, call.completion_tokens, call.cached_tokens) == (None, None, None)


class TestFailedCallsAreRecordedToo:
    """失敗した呼び出しも記録に残し、呼び出し元への例外は変えないことを保証する。"""

    def test_api_error_records_failure_and_still_raises(self) -> None:
        """API 呼び出しが例外を投げると、success=False と error_code を 1 件残してから LlmApiCallException を投げる。"""
        sink = _Sink()
        client = _client(sink)
        with patch(_LITELLM) as m_litellm:
            m_litellm.completion.side_effect = ValueError("boom")
            with pytest.raises(LlmApiCallException) as exc_info:
                client.complete_episode_writing_json([{"role": "user", "content": "x"}])

        assert len(sink.calls) == 1
        call = sink.calls[0]
        assert call.component is AuxLlmComponent.EPISODE_WRITING
        assert call.success is False
        assert call.error_code == exc_info.value.error_code == "LLM_API_CALL_FAILED"
        assert (call.prompt_tokens, call.cost_usd) == (None, None)

    def test_invalid_json_records_failure_with_tokens_already_spent(self) -> None:
        """応答が JSON でないとき、success=False と error_code に加え、使ったトークンと費用も残す。"""
        sink = _Sink()
        client = _client(sink)
        with patch(_LITELLM) as m_litellm:
            m_litellm.completion.return_value = _response(
                "not json", usage=_usage(prompt=200, completion=40, cached=0, cost=0.001)
            )
            with pytest.raises(LlmApiCallException):
                client.complete_belief_consolidation_json([{"role": "user", "content": "x"}])

        call = sink.calls[0]
        assert call.success is False
        assert call.error_code == "LLM_EPISODE_SUBJECTIVE_INVALID_JSON"
        assert (call.prompt_tokens, call.completion_tokens) == (200, 40)
        assert call.cost_usd == pytest.approx(0.001)


class TestRecordingFailureDoesNotStopTheCall:
    """記録の失敗が記憶の部品の呼び出しを倒さないことを保証する。"""

    def test_broken_sink_still_returns_parsed_result(self) -> None:
        """sink.record が例外を投げても、呼び出しはパース済みの結果を返す。"""
        client = _client(_BrokenSink())
        with patch(_LITELLM) as m_litellm:
            m_litellm.completion.return_value = _response(
                '{"ok": true}', usage=_usage(prompt=1, completion=1, cached=0, cost=0.0)
            )
            result = client.complete_short_term_summary_json([{"role": "user", "content": "x"}])

        assert result == {"ok": True}
