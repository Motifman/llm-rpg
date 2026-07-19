"""解決済み設定からの LLM クライアント構成を保証する。"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.wiring._llm_client_factory import (
    create_llm_client_from_config,
)
from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
    ResolvedLlmRuntimeConfig,
)


class TestCreateLlmClientFromConfig:
    """環境変数ではなく ``ResolvedLlmRuntimeConfig`` だけからクライアントを作る。"""

    def test_litellm_uses_model_from_config(self) -> None:
        """``llm_model`` 指定時にそのモデル文字列になる。"""
        cfg = ResolvedLlmRuntimeConfig.for_tests(
            llm_client_kind="litellm",
            llm_model="anthropic/foo-bar",
        )

        client = create_llm_client_from_config(cfg)

        assert getattr(client, "_model", None) == "anthropic/foo-bar"

    def test_litellm_falls_back_to_default_when_model_unset(self) -> None:
        """``llm_model`` 未設定ならインフラ側の既定モデルになる。"""
        from ai_rpg_world.infrastructure.llm.litellm_client import DEFAULT_LLM_MODEL

        cfg = ResolvedLlmRuntimeConfig.for_tests(llm_client_kind="litellm")

        client = create_llm_client_from_config(cfg)

        assert getattr(client, "_model", None) == DEFAULT_LLM_MODEL

    def test_stub_client_when_config_is_stub(self) -> None:
        """``llm_client_kind=stub`` は StubLlmClient を返す。"""
        client = create_llm_client_from_config(ResolvedLlmRuntimeConfig.for_tests())

        assert isinstance(client, StubLlmClient)

