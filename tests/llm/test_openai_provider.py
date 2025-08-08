import types
import sys

import pytest

from game.llm.providers.base import CompletionRequest
from game.llm.providers.openai import OpenAIClient


class _DummyChoices:
    def __init__(self, text: str):
        self.choices = [types.SimpleNamespace(message=types.SimpleNamespace(content=text))]
        self.usage = types.SimpleNamespace(prompt_tokens=5, completion_tokens=7)


class _DummyChat:
    def __init__(self, text: str):
        self._text = text

    def completions(self):  # pragma: no cover - accessed as attribute
        pass

    @property
    def completions(self):
        return types.SimpleNamespace(create=lambda **kwargs: _DummyChoices(self._text))


class _DummyOpenAI:
    def __init__(self, text: str):
        self.chat = types.SimpleNamespace(completions=_DummyChat(text))


def test_openai_client_complete_monkeypatch(monkeypatch):
    dummy = _DummyOpenAI(text="{\"ok\": true}")

    def _fake_import(name, *args, **kwargs):  # pragma: no cover - monkeypatch target
        if name == "openai":
            return dummy
        return __import__(name, *args, **kwargs)

    # sys.modules に直接差し込む
    sys.modules["openai"] = dummy

    client = OpenAIClient(api_key="test", model="gpt-test")
    req = CompletionRequest(prompt="hello", system_prompt="sys", temperature=0.1, max_tokens=16, json_schema={})
    resp = client.complete(req)

    assert resp.text == "{\"ok\": true}"
    assert resp.parsed_json == {"ok": True}
    assert resp.usage_prompt_tokens == 5
    assert resp.usage_completion_tokens == 7


