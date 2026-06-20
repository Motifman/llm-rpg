"""optional_llm_services (経路統一 R2c-1): LiteLLM クライアント有無で optional な
LLM サービス/ポートを解決する共有ヘルパの単体テスト。

full wiring 本体 (create_llm_agent_wiring) から escape も使う依存として切り出したもの。
判定は「LiteLLM のときだけ実体を返し、それ以外 (stub 等) は None」。
"""

from __future__ import annotations

from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient
from ai_rpg_world.application.llm.wiring.optional_llm_services import (
    optional_episodic_reinterpretation_completion,
    optional_semantic_gist_service,
)


class TestOptionalSemanticGistService:
    """SEMANTIC_LLM_GIST gist service の optional 解決。"""

    def test_disabled_returns_none(self) -> None:
        """enabled=False なら client によらず None。"""
        assert optional_semantic_gist_service(StubLlmClient(None), False) is None

    def test_non_litellm_client_returns_none(self) -> None:
        """enabled でも非 LiteLLM (stub) なら None (= 決定論 gist にフォールバック)。"""
        assert optional_semantic_gist_service(StubLlmClient(None), True) is None


class TestOptionalEpisodicReinterpretationCompletion:
    """reinterpretation completion ポートの optional 解決。"""

    def test_explicit_port_is_returned_as_is(self) -> None:
        """explicit 指定があれば client によらずそれを返す。"""
        sentinel = object()
        assert (
            optional_episodic_reinterpretation_completion(StubLlmClient(None), sentinel)
            is sentinel
        )

    def test_non_litellm_without_explicit_returns_none(self) -> None:
        """explicit 無し + 非 LiteLLM (stub) なら None。"""
        assert (
            optional_episodic_reinterpretation_completion(StubLlmClient(None), None)
            is None
        )
