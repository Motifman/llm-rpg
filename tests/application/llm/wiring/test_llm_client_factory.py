"""環境変数からの LLM クライアント構成（モデル指定など）。"""

from __future__ import annotations

import pytest

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient


class TestCreateLlmClientFromEnv:
    """create_llm_client_from_env の挙動。"""

    def test_litellm_uses_llm_model_env_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LLM_CLIENT=litellm かつ LLM_MODEL 指定時にそのモデル文字列になる。"""
        monkeypatch.setenv("LLM_CLIENT", "litellm")
        monkeypatch.setenv("LLM_MODEL", " anthropic/foo-bar ")
        from ai_rpg_world.application.llm.wiring._llm_client_factory import (
            create_llm_client_from_env,
        )

        client = create_llm_client_from_env()
        assert getattr(client, "_model", None) == "anthropic/foo-bar"

    def test_litellm_falls_back_to_default_when_llm_model_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """LLM_MODEL 未設定ならインフラ側の既定モデルになる。"""
        monkeypatch.setenv("LLM_CLIENT", "litellm")
        monkeypatch.delenv("LLM_MODEL", raising=False)
        from ai_rpg_world.application.llm.wiring._llm_client_factory import (
            create_llm_client_from_env,
        )
        from ai_rpg_world.infrastructure.llm.litellm_client import DEFAULT_LLM_MODEL

        client = create_llm_client_from_env()
        assert getattr(client, "_model", None) == DEFAULT_LLM_MODEL

    def test_stub_client_when_llm_client_is_stub(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """既定の stub パスは StubLlmClient を返す。"""
        monkeypatch.setenv("LLM_CLIENT", "stub")
        from ai_rpg_world.application.llm.wiring._llm_client_factory import (
            create_llm_client_from_env,
        )

        client = create_llm_client_from_env()
        assert isinstance(client, StubLlmClient)
