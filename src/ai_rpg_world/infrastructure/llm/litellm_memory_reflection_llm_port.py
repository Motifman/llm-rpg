"""LiteLLM 経由の Memory Reflection 用ポート。"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

import litellm
from litellm import AuthenticationError as LitellmAuthenticationError
from litellm import RateLimitError as LitellmRateLimitError

from ai_rpg_world.application.llm.contracts.interfaces import IMemoryReflectionLlmPort
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient


class LiteLlmMemoryReflectionLlmPort(IMemoryReflectionLlmPort):
    """`litellm.completion` で system/user のみ送信。"""

    def __init__(self, client: LiteLLMClient) -> None:
        if not isinstance(client, LiteLLMClient):
            raise TypeError("client must be LiteLLMClient")
        self._client = client
        self._logger = logging.getLogger(self.__class__.__name__)

    def complete(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not isinstance(system_prompt, str):
            raise TypeError("system_prompt must be str")
        if not isinstance(user_prompt, str):
            raise TypeError("user_prompt must be str")
        kw: Dict[str, Any] = {
            **self._client.completion_base_kwargs(),
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if response_format is not None:
            kw["response_format"] = response_format
        try:
            response = litellm.completion(**kw)
        except Exception as e:
            self._logger.exception("LiteLLM memory reflection completion failed: %s", e)
            error_code = "LLM_API_CALL_FAILED"
            if isinstance(e, LitellmAuthenticationError):
                error_code = "LLM_AUTHENTICATION_ERROR"
            elif isinstance(e, LitellmRateLimitError):
                error_code = "LLM_RATE_LIMIT"
            raise LlmApiCallException(
                f"LLM API call failed: {e}",
                error_code=error_code,
                cause=e,
            ) from e

        if not response or not getattr(response, "choices", None) or len(response.choices) == 0:
            return ""
        message = response.choices[0].message
        if not message:
            return ""
        content = getattr(message, "content", None)
        return (content or "").strip()
