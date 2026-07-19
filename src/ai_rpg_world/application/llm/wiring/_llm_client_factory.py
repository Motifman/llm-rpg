"""LLM クライアントのファクトリ。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ai_rpg_world.application.llm.ports.llm_client_port import ILLMClient
from ai_rpg_world.application.llm.services.llm_client_stub import StubLlmClient

if TYPE_CHECKING:
    from ai_rpg_world.application.llm.wiring.resolved_runtime_config import (
        ResolvedLlmRuntimeConfig,
    )

_VALID_LLM_CLIENT_VALUES = frozenset({"stub", "litellm"})


def create_llm_client_from_config(config: "ResolvedLlmRuntimeConfig") -> ILLMClient:
    """解決済み設定に応じて ILLMClient 実装を返す。

    引数は必ず ``ResolvedLlmRuntimeConfig``。フィールドは直接参照する
    (``getattr(config, name, default)`` の縮退を使わない): フィールド名 typo や
    誤った型の config を渡したら黙って stub / default に縮退せず AttributeError で
    落ち、静かな失敗にしない。
    """
    value = config.llm_client_kind.strip().lower()
    if value not in _VALID_LLM_CLIENT_VALUES:
        raise ValueError(
            f"llm_client_kind must be one of {sorted(_VALID_LLM_CLIENT_VALUES)}, got: {value!r}"
        )
    if value == "litellm":
        from ai_rpg_world.infrastructure.llm.litellm_client import (
            DEFAULT_LLM_MODEL,
            LiteLLMClient,
        )

        configured = (config.llm_model or "").strip()
        return LiteLLMClient(
            model=(configured or DEFAULT_LLM_MODEL),
            api_key=config.llm_api_key,
            api_base=config.llm_api_base,
            timeout_seconds=config.llm_request_timeout_seconds,
            openrouter_provider=config.openrouter_provider,
            openrouter_quantization=config.openrouter_quantization,
            openrouter_require_params=bool(config.openrouter_require_params),
            reasoning_effort=config.llm_reasoning_effort,
            wall_cap_seconds=config.llm_wall_time_cap_seconds,
            rate_limit_retry_attempts=int(config.llm_rate_limit_retry_attempts),
            rate_limit_retry_base_sleep=float(config.llm_rate_limit_retry_base_sleep),
        )
    return StubLlmClient()
