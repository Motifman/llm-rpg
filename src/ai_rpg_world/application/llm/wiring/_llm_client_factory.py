"""LLM クライアントと subagent 用 invoke のファクトリ。"""

import os
from typing import Callable

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


def create_subagent_invoke_text(client: ILLMClient) -> Callable[[str, str], str]:
    """subagent 用のテキスト完了呼び出しを返す。"""
    if client is None or isinstance(client, StubLlmClient):
        return lambda _sys, _user: "（subagent はスタブです。実 LLM 設定時に要約が返ります。）"

    try:
        from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient
        if isinstance(client, LiteLLMClient):
            import litellm
            def _invoke(system: str, user: str) -> str:
                r = litellm.completion(
                    model=client._model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    api_key=client._api_key,
                )
                if r and r.choices:
                    content = getattr(r.choices[0].message, "content", None)
                    return (content or "").strip()
                return ""
            return _invoke
    except ImportError:
        pass
    return lambda _sys, _user: "（subagent は未対応のクライアントです）"
