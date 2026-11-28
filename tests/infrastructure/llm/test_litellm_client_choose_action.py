from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from ai_rpg_world.being.application.choose_action import ActionChoosingReply, ToolCallReply
from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient


@pytest.fixture(autouse=True)
def isolate_litellm_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("OPENAI_API_BASE", "OPENROUTER_PROVIDER", "OPENROUTER_QUANTIZATION", "LLM_REASONING_EFFORT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("ai_rpg_world.infrastructure.llm.litellm_client._load_dotenv_if_available", lambda: None)


class _Invoke:
    def __init__(self, returned: dict[str, Any] | None, *, finish_reason: str | None, reasoning_effort: str | None):
        self._returned = returned
        self._metrics = SimpleNamespace(finish_reason=finish_reason, reasoning_effort=reasoning_effort)
        self.calls: list[dict[str, Any]] = []

    def __call__(self, messages: Any, tools: Any, tool_choice: Any, **kwargs: Any) -> dict[str, Any] | None:
        self.calls.append({"tool_choice": tool_choice, **kwargs})
        kwargs["metrics_sink"].record(self._metrics)
        return self._returned


def _client(monkeypatch: pytest.MonkeyPatch, invoke: _Invoke) -> LiteLLMClient:
    client = LiteLLMClient(model="openai/gpt-5-mini", api_key="sk-dummy")
    monkeypatch.setattr(client, "invoke", invoke)
    return client


class TestLiteLLMClientChooseAction:
    """LiteLLMClient.choose_action が、invoke の戻り値と計測を、Being の行動の答えに写すことを保証する。"""

    def test_tool_call_becomes_the_reply(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """invoke が返したツールの名前・引数・呼び出しの ID が、そのまま答えに入り、tool_choice は required で送る。"""
        invoke = _Invoke(
            {"name": "interact", "arguments": {"target": "金庫"}, "tool_call_id": "call_1"},
            finish_reason="tool_calls",
            reasoning_effort="high",
        )

        reply = _client(monkeypatch, invoke).choose_action([], [], reasoning_off=False)

        assert reply == ActionChoosingReply(
            tool_call=ToolCallReply(tool_name="interact", arguments={"target": "金庫"}, call_id="call_1")
        )
        assert invoke.calls[0]["tool_choice"] == "required" and invoke.calls[0]["reasoning_effort"] is None

    def test_reply_cut_off_while_reasoning_is_marked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """考えを有効にした呼び出しが出力の上限 (length) で打ち切られ、ツールが返らなければ、その印が付く。"""
        invoke = _Invoke(None, finish_reason="length", reasoning_effort="high")

        reply = _client(monkeypatch, invoke).choose_action([], [], reasoning_off=False)

        assert reply == ActionChoosingReply(tool_call=None, cut_off_while_reasoning=True)

    def test_reasoning_off_sends_reasoning_effort_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """考えを止めて呼ぶときは reasoning_effort に none を渡し、上限で切れても打ち切りの印は付けない。"""
        invoke = _Invoke(None, finish_reason="length", reasoning_effort="none")

        reply = _client(monkeypatch, invoke).choose_action([], [], reasoning_off=True)

        assert invoke.calls[0]["reasoning_effort"] == "none" and not reply.cut_off_while_reasoning


class TestPromptCaptureOfChooseAction:
    """LiteLLMClient.choose_action が、書き出しの文脈を渡されたときだけ invoke に渡し、古い世界の呼び方では渡さないことを保証する。"""

    def test_without_a_context_nothing_is_passed_to_invoke(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """文脈を渡さない古い世界の呼び方では、invoke の prompt_capture_context は None のまま。"""
        invoke = _Invoke(None, finish_reason="stop", reasoning_effort=None)

        _client(monkeypatch, invoke).choose_action([], [], reasoning_off=False)

        assert invoke.calls[0]["prompt_capture_context"] is None

    def test_given_context_is_passed_to_invoke(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """文脈を渡すと、そのまま invoke に渡り、生の返事ごと書き出される。"""
        invoke = _Invoke(None, finish_reason="stop", reasoning_effort=None)
        context = object()

        _client(monkeypatch, invoke).choose_action([], [], reasoning_off=False, prompt_capture_context=context)

        assert invoke.calls[0]["prompt_capture_context"] is context
