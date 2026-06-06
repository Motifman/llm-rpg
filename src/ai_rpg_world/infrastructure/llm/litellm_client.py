"""
LiteLLM を用いた ILLMClient 実装。

API Key: コンストラクタで api_key を渡さない場合は環境変数 OPENAI_API_KEY を参照する。
api_key 未指定時は .env を自動で読み込み、その後に環境変数を参照する。
.env は .gitignore に含めること。

OpenAI 互換エンドポイント（SSH 越しの vLLM 等）: ``OPENAI_API_BASE`` に
``http://127.0.0.1:8000/v1`` のようなベース URL を設定する。
その場合 OPENAI_API_KEY が空でも ``EMPTY`` を送り続行する（vLLM 既定の無認証構成向け）。
"""

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional

import litellm
from litellm import AuthenticationError as LitellmAuthenticationError
from litellm import RateLimitError as LitellmRateLimitError

from ai_rpg_world.application.llm.contracts.episodic_chunk_subjective_llm_port import (
    IEpisodicChunkSubjectiveCompletionPort,
)
from ai_rpg_world.application.llm.contracts.episodic_reinterpretation import (
    IEpisodicReinterpretationCompletionPort,
)
from ai_rpg_world.application.llm.contracts.interfaces import ILLMClient
from ai_rpg_world.application.llm.contracts.llm_call_metrics import (
    LlmCallMetrics,
    LlmCallMetricsSink,
)
from ai_rpg_world.application.llm.exceptions import LlmApiCallException

_DEFAULT_MODEL = "openai/gpt-5-mini"
DEFAULT_LLM_MODEL = _DEFAULT_MODEL
_ENV_VAR_API_KEY = "OPENAI_API_KEY"
_ENV_VAR_API_BASE = "OPENAI_API_BASE"
_VLLM_DEFAULT_PLACEHOLDER_KEY = "EMPTY"


def _extract_first_json_object(text: str) -> str:
    """JSON mode が崩れて前後テキストやコードフェンスを含む応答から JSON object を抜き出す。"""
    stripped = text.strip()
    if not stripped:
        return stripped
    stripped = re.sub(
        r"<think>[\s\S]*?</think>",
        "",
        stripped,
        flags=re.IGNORECASE,
    )
    stripped = re.sub(
        r"<redacted_reasoning>[\s\S]*?</redacted_reasoning>",
        "",
        stripped,
        flags=re.IGNORECASE,
    ).strip()
    try:
        obj = json.loads(stripped)
        return json.dumps(obj, ensure_ascii=False)
    except (json.JSONDecodeError, TypeError):
        pass
    start = stripped.find("{")
    if start < 0:
        return stripped
    depth = 0
    for idx in range(start, len(stripped)):
        char = stripped[idx]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return stripped[start : idx + 1]
    return stripped


def _load_dotenv_if_available() -> None:
    """python-dotenv が利用可能なら .env を読み込む。"""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


class LiteLLMClient(
    ILLMClient,
    IEpisodicChunkSubjectiveCompletionPort,
    IEpisodicReinterpretationCompletionPort,
):
    """
    LiteLLM の completion API で messages + tools を送り、1 つの tool_call を返す実装。
    tool_choice="required" で 1 ツール必須とする。
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        api_key: Optional[str] = None,
        api_key_env_var: str = _ENV_VAR_API_KEY,
        api_base: Optional[str] = None,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
        if not isinstance(api_key_env_var, str) or not api_key_env_var.strip():
            raise ValueError("api_key_env_var must be a non-empty string")
        if api_key is not None and not isinstance(api_key, str):
            raise TypeError("api_key must be str or None")
        if api_base is not None and not isinstance(api_base, str):
            raise TypeError("api_base must be str or None")
        if api_key is None or api_base is None:
            _load_dotenv_if_available()
        self._model = model.strip()
        self._api_key_env_var = api_key_env_var
        if api_key is not None:
            # 明示的に渡されたとき（空文字含む）はその値を使う。カスタム base 無しかつ空なら invoke で LLM_API_KEY_MISSING。
            self._api_key = (api_key.strip() if isinstance(api_key, str) else "")
        else:
            self._api_key = (os.environ.get(api_key_env_var) or "").strip()

        resolved_base = ""
        if api_base is not None:
            resolved_base = api_base.strip()
        else:
            resolved_base = (os.environ.get(_ENV_VAR_API_BASE) or "").strip()
        self._api_base = resolved_base or None

        self._logger = logging.getLogger(self.__class__.__name__)

    def _lite_api_key(self) -> str:
        """litellm.completion に渡す API キー（vLLM 向けカスタム base では空でもプレースホルダを使う）。"""
        raw = self._api_key.strip() if isinstance(self._api_key, str) else ""
        if self._api_base:
            return raw if raw else _VLLM_DEFAULT_PLACEHOLDER_KEY
        return raw

    def _assert_can_call_litellm(self) -> None:
        if self._lite_api_key():
            return
        raise LlmApiCallException(
            f"API key is not set. Set {self._api_key_env_var} or pass api_key to the client.",
            error_code="LLM_API_KEY_MISSING",
        )

    def completion_base_kwargs(self) -> Dict[str, Any]:
        """ツール無しの chat completion 用（Episode Encoder 等）。カスタム base 無しでは api_key が必須。"""
        self._assert_can_call_litellm()
        base: Dict[str, Any] = {"model": self._model, "api_key": self._lite_api_key()}
        if self._api_base is not None:
            base["api_base"] = self._api_base
        return base

    def invoke(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        tool_choice: str = "required",
        *,
        metrics_sink: Optional[LlmCallMetricsSink] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        1 回の LLM 呼び出しを行い、tool_call があれば {"name": str, "arguments": dict} を返す。
        tool_call が無い場合やパースに失敗した場合は None を返す。
        API エラー時は LlmApiCallException を投げる。

        ``metrics_sink`` が渡された場合、呼び出し成否によらず ``LlmCallMetrics`` を 1 件
        sink に流す (実験 #356: τ_sim 設定根拠 + scenario cost 評価用)。
        """
        self._assert_can_call_litellm()
        start_monotonic = time.monotonic()
        try:
            completion_kw: Dict[str, Any] = {
                "model": self._model,
                "messages": messages,
                "tools": tools,
                "tool_choice": tool_choice,
                "api_key": self._lite_api_key(),
            }
            if self._api_base is not None:
                completion_kw["api_base"] = self._api_base
            response = litellm.completion(**completion_kw)
        except Exception as e:
            wall_latency_ms = int((time.monotonic() - start_monotonic) * 1000)
            error_code = "LLM_API_CALL_FAILED"
            if isinstance(e, LitellmAuthenticationError):
                error_code = "LLM_AUTHENTICATION_ERROR"
            elif isinstance(e, LitellmRateLimitError):
                error_code = "LLM_RATE_LIMIT"
            self._emit_metrics(
                metrics_sink,
                wall_latency_ms=wall_latency_ms,
                prompt_tokens=0,
                completion_tokens=0,
                success=False,
                error_code=error_code,
            )
            self._logger.exception("LiteLLM completion failed: %s", e)
            raise LlmApiCallException(
                f"LLM API call failed: {e}",
                error_code=error_code,
                cause=e,
            ) from e
        wall_latency_ms = int((time.monotonic() - start_monotonic) * 1000)
        prompt_tokens, completion_tokens = self._extract_token_usage(response)
        tool_call = self._parse_tool_call(response, messages, tools)
        self._emit_metrics(
            metrics_sink,
            wall_latency_ms=wall_latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            success=tool_call is not None,
            error_code=None if tool_call is not None else "NO_TOOL_CALL",
        )
        return tool_call

    @staticmethod
    def _extract_token_usage(response: Any) -> tuple[int, int]:
        """litellm レスポンスから (prompt_tokens, completion_tokens) を best-effort で取得する。

        litellm は OpenAI 互換の usage を返すことが多いが、provider 差で None /
        欠落することもある。欠落時は 0 を返す (TPS は 0 になる)。
        """
        try:
            usage = getattr(response, "usage", None)
            if usage is None:
                return 0, 0
            prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
            completion = int(getattr(usage, "completion_tokens", 0) or 0)
            return prompt, completion
        except Exception:
            return 0, 0

    def _emit_metrics(
        self,
        sink: Optional[LlmCallMetricsSink],
        *,
        wall_latency_ms: int,
        prompt_tokens: int,
        completion_tokens: int,
        success: bool,
        error_code: Optional[str],
    ) -> None:
        if sink is None:
            return
        try:
            metrics = LlmCallMetrics(
                model=self._model,
                wall_latency_ms=wall_latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                tps=LlmCallMetrics.compute_tps(completion_tokens, wall_latency_ms),
                success=success,
                error_code=error_code,
            )
            sink.record(metrics)
        except Exception:
            # メトリクス記録の失敗が LLM 呼び出し本体の挙動を倒さないよう吸収。
            self._logger.exception("metrics_sink.record failed")

    def complete_episode_subjective_json(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        tools 無しで JSON object を強制する chat completion を行いパース済み dict を返す。
        失敗や不正 JSON ではここでは補完せず LlmApiCallException を送出し、呼び出し元が草案テンプレへフォールバックする。
        """
        kwargs = self.completion_base_kwargs()
        try:
            response = litellm.completion(
                messages=messages,
                response_format={"type": "json_object"},
                **kwargs,
            )
        except Exception as e:
            self._logger.exception("LiteLLM subjective completion failed: %s", e)
            error_code = "LLM_API_CALL_FAILED"
            if isinstance(e, LitellmAuthenticationError):
                error_code = "LLM_AUTHENTICATION_ERROR"
            elif isinstance(e, LitellmRateLimitError):
                error_code = "LLM_RATE_LIMIT"
            raise LlmApiCallException(
                f"LLM subjective completion failed: {e}",
                error_code=error_code,
                cause=e,
            ) from e
        if not response or not getattr(response, "choices", None) or len(response.choices) == 0:
            raise LlmApiCallException(
                "Empty response from subjective completion",
                error_code="LLM_EPISODE_SUBJECTIVE_EMPTY_RESPONSE",
            )
        message = response.choices[0].message
        content = getattr(message, "content", None) if message else None
        if not isinstance(content, str) or not content.strip():
            raise LlmApiCallException(
                "Missing message content from subjective completion",
                error_code="LLM_EPISODE_SUBJECTIVE_EMPTY_CONTENT",
            )
        extracted_content = _extract_first_json_object(content)
        try:
            parsed = json.loads(extracted_content)
        except (json.JSONDecodeError, TypeError) as e:
            raise LlmApiCallException(
                f"Subjective completion content is not valid JSON: {e}",
                error_code="LLM_EPISODE_SUBJECTIVE_INVALID_JSON",
                cause=e,
            ) from e
        if not isinstance(parsed, dict):
            raise LlmApiCallException(
                "Subjective completion JSON root must be an object",
                error_code="LLM_EPISODE_SUBJECTIVE_INVALID_JSON",
            )
        return parsed

    def complete_episodic_reinterpretation_json(
        self,
        messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """tools 無しで想起後再解釈 JSON object を返す。"""
        return self.complete_episode_subjective_json(messages)

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
