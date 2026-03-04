"""StubLlmClient のテスト（正常・境界）"""

import pytest

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient


class TestStubLlmClient:
    """StubLlmClient の正常・境界ケース"""

    def test_invoke_returns_none_when_not_set(self):
        """tool_call を設定していないとき invoke は None を返す"""
        client = StubLlmClient()
        result = client.invoke([], [], "required")
        assert result is None

    def test_invoke_returns_configured_tool_call(self):
        """set した tool_call が invoke で返る"""
        client = StubLlmClient(tool_call_to_return={"name": "world_no_op", "arguments": {}})
        result = client.invoke(
            [{"role": "user", "content": "test"}],
            [{"type": "function", "function": {"name": "world_no_op", "description": "", "parameters": {}}}],
            "required",
        )
        assert result is not None
        assert result["name"] == "world_no_op"
        assert result["arguments"] == {}

    def test_set_tool_call_to_return_updates_next_invoke(self):
        """set_tool_call_to_return で次回の invoke の戻りが変わる"""
        client = StubLlmClient(tool_call_to_return={"name": "a", "arguments": {}})
        assert client.invoke([], [], "required")["name"] == "a"
        client.set_tool_call_to_return({"name": "b", "arguments": {"x": 1}})
        r = client.invoke([], [], "required")
        assert r["name"] == "b"
        assert r["arguments"] == {"x": 1}

    def test_set_tool_call_to_return_none_returns_none(self):
        """set_tool_call_to_return(None) で invoke が None を返す"""
        client = StubLlmClient(tool_call_to_return={"name": "x", "arguments": {}})
        client.set_tool_call_to_return(None)
        assert client.invoke([], [], "required") is None
