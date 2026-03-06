"""
LiteLLM を用いた ILLMClient 実装。

API Key: コンストラクタで api_key を渡さない場合は環境変数 OPENAI_API_KEY を参照する。
api_key 未指定時は .env を自動で読み込み、その後に環境変数を参照する。
.env は .gitignore に含めること。
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional

import litellm
from litellm import AuthenticationError as LitellmAuthenticationError
from litellm import RateLimitError as LitellmRateLimitError

from ai_rpg_world.application.llm.contracts.interfaces import ILLMClient
from ai_rpg_world.application.llm.exceptions import LlmApiCallException

_DEFAULT_MODEL = "openai/gpt-5-mini"
_ENV_VAR_API_KEY = "OPENAI_API_KEY"


def _load_dotenv_if_available() -> None:
    """python-dotenv が利用可能なら .env を読み込む。"""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


class LiteLLMClient(ILLMClient):
    """
    LiteLLM の completion API で messages + tools を送り、1 つの tool_call を返す実装。
    tool_choice="required" で 1 ツール必須とする。
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        api_key: Optional[str] = None,
        api_key_env_var: str = _ENV_VAR_API_KEY,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
        if not isinstance(api_key_env_var, str) or not api_key_env_var.strip():
            raise ValueError("api_key_env_var must be a non-empty string")
        if api_key is not None and not isinstance(api_key, str):
            raise TypeError("api_key must be str or None")
        self._model = model.strip()
        self._api_key_env_var = api_key_env_var
        if api_key is not None:
            # 明示的に渡されたとき（空文字含む）はその値を使う。空なら invoke で LLM_API_KEY_MISSING になる。
            self._api_key = (api_key.strip() if isinstance(api_key, str) else "")
        else:
            _load_dotenv_if_available()
            self._api_key = (os.environ.get(api_key_env_var) or "").strip()
        self._logger = logging.getLogger(self.__class__.__name__)

    def invoke(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "required",
    ) -> Optional[Dict[str, Any]]:
        """
        1 回の LLM 呼び出しを行い、tool_call があれば {"name": str, "arguments": dict} を返す。
        tool_call が無い場合やパースに失敗した場合は None を返す。
        API エラー時は LlmApiCallException を投げる。
        """
        if not self._api_key:
            raise LlmApiCallException(
                f"API key is not set. Set {self._api_key_env_var} or pass api_key to the client.",
                error_code="LLM_API_KEY_MISSING",
            )
        try:
            response = litellm.completion(
                model=self._model,
                messages=messages,
                tools=tools,
                tool_choice=tool_choice,
                api_key=self._api_key,
            )
        except Exception as e:
            self._logger.exception("LiteLLM completion failed: %s", e)
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

        return self._parse_tool_call(response, messages, tools)

    def _parse_tool_call(
        self,
        response: Any,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        """response から先頭の tool_call を取り出し {"name": str, "arguments": dict} で返す。"""
        if not response or not getattr(response, "choices", None) or len(response.choices) == 0:
            return None
        message = response.choices[0].message
        if not message:
            return None
        tool_calls = getattr(message, "tool_calls", None) or []
        if not tool_calls:
            return None
        first = tool_calls[0]
        name = getattr(getattr(first, "function", None), "name", None)
        args_str = getattr(getattr(first, "function", None), "arguments", None)
        if not name:
            return None
        arguments: Dict[str, Any] = {}
        if args_str and isinstance(args_str, str):
            try:
                arguments = json.loads(args_str) if args_str.strip() else {}
            except (json.JSONDecodeError, TypeError):
                arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        return {"name": name, "arguments": arguments}
