"""LLM クライアントのファクトリ。"""

import os

from ai_rpg_world.application.llm.contracts.interfaces import ILLMClient
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient

_VALID_LLM_CLIENT_VALUES = frozenset({"stub", "litellm"})
_ENV_LLM_CLIENT = "LLM_CLIENT"
_DEFAULT_LLM_CLIENT = "stub"


def create_llm_client_from_env() -> ILLMClient:
    """環境変数 LLM_CLIENT に応じて ILLMClient 実装を返す。stub（デフォルト） or litellm。未知の値は ValueError。"""
    value = (os.environ.get(_ENV_LLM_CLIENT) or _DEFAULT_LLM_CLIENT).strip().lower()
    if value not in _VALID_LLM_CLIENT_VALUES:
        raise ValueError(
            f"LLM_CLIENT must be one of {sorted(_VALID_LLM_CLIENT_VALUES)}, got: {value!r}"
        )
    if value == "litellm":
        from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient
        return LiteLLMClient()
    return StubLlmClient()
