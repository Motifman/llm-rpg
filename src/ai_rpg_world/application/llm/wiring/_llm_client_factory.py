"""LLM クライアントのファクトリ。"""

from ai_rpg_world.application.llm.ports.llm_client_port import ILLMClient
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient

_VALID_LLM_CLIENT_VALUES = frozenset({"stub", "litellm"})
_DEFAULT_LLM_CLIENT = "stub"


def create_llm_client_from_config(config: object) -> ILLMClient:
    """解決済み設定に応じて ILLMClient 実装を返す。"""
    value = (getattr(config, "llm_client_kind", None) or _DEFAULT_LLM_CLIENT).strip().lower()
    if value not in _VALID_LLM_CLIENT_VALUES:
        raise ValueError(
            f"llm_client_kind must be one of {sorted(_VALID_LLM_CLIENT_VALUES)}, got: {value!r}"
        )
    if value == "litellm":
        from ai_rpg_world.infrastructure.llm.litellm_client import (
            DEFAULT_LLM_MODEL,
            LiteLLMClient,
        )

        configured = (getattr(config, "llm_model", None) or "").strip()
        return LiteLLMClient(
            model=(configured or DEFAULT_LLM_MODEL),
            api_key=getattr(config, "llm_api_key", None),
            api_base=getattr(config, "llm_api_base", None),
            timeout_seconds=getattr(config, "llm_request_timeout_seconds", None),
            openrouter_provider=getattr(config, "openrouter_provider", None),
            openrouter_quantization=getattr(config, "openrouter_quantization", None),
            openrouter_require_params=bool(
                getattr(config, "openrouter_require_params", False)
            ),
            reasoning_effort=getattr(config, "llm_reasoning_effort", "none"),
            wall_cap_seconds=getattr(config, "llm_wall_time_cap_seconds", None),
            rate_limit_retry_attempts=int(
                getattr(config, "llm_rate_limit_retry_attempts", 3)
            ),
            rate_limit_retry_base_sleep=float(
                getattr(config, "llm_rate_limit_retry_base_sleep", 2.0)
            ),
        )
    return StubLlmClient()
