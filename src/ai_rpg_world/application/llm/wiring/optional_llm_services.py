"""LLM クライアント有無で optional な LLM サービスを解決する共有ヘルパ (経路統一 R2c-1)。

元は ``wiring/__init__.py`` (full wiring = create_llm_agent_wiring) 内の private 関数
だったが、escape runtime もこれに依存しており、full wiring 本体
(create_llm_agent_wiring / LlmAgentOrchestrator) を退役 (R2c-2) する前に、
**symbol 依存だけ**を独立モジュールへ切り出す。
(注: 本モジュールは ``wiring`` package 配下なので import すると ``wiring/__init__.py`` も
ロードされる = import-time の full wiring 依存は残る。これは R2c-2 で __init__ から full
wiring 本体を削除して軽量化することで解消する。)

「LiteLLM クライアントのときだけ実 LLM サービスを返し、それ以外は None」という判定で、
full wiring 固有のロジックには依存しない。
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_rpg_world.application.llm.ports.llm_client_port import ILLMClient

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.services.semantic_gist_service import (
        SemanticGistService,
    )


def optional_semantic_gist_service(
    llm_client: ILLMClient,
    enabled: bool,
) -> SemanticGistService | None:
    """``SEMANTIC_LLM_GIST_ENABLED=1`` かつ LiteLLM クライアントあるときだけ
    ``SemanticGistService`` を返す。

    Phase 1b: gist 生成の LLM 化。OFF または非 LiteLLM の場合は None を返し、
    promotion service は既存の決定論 gist を使う。
    """
    if not enabled:
        return None
    from ai_rpg_world.application.llm.ports.semantic_gist_completion_port import (
        ISemanticGistCompletionPort,
    )
    from ai_rpg_world.application.llm.services.semantic_gist_service import (
        SemanticGistService,
    )
    from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient

    if not isinstance(llm_client, LiteLLMClient):
        return None
    port: ISemanticGistCompletionPort = llm_client
    return SemanticGistService(port)


__all__ = [
    "optional_semantic_gist_service",
]
