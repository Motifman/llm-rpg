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
import copy
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
from ai_rpg_world.application.llm.contracts.semantic_gist_completion_port import (
    ISemanticGistCompletionPort,
)
from ai_rpg_world.application.llm.contracts.short_term_memory import (
    IShortTermMemoryLongSummaryCompletionPort,
    IShortTermMemorySummaryCompletionPort,
)
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

# OpenRouter provider routing 用の env 群。
# `OPENROUTER_PROVIDER=DeepInfra OPENROUTER_QUANTIZATION=fp8` のように指定すると
# 全 litellm.completion 呼び出しに `extra_body.provider.{order, quantizations,
# require_parameters, allow_fallbacks}` を注入する。
# OpenRouter docs: https://openrouter.ai/docs/provider-routing
#
# なぜ必要か: api_base=https://openrouter.ai/api/v1 で叩くと OpenRouter が
# provider を自由に選ぶ。例えば Gemma 4 31B では DeepInfra が turbo (fp4) /
# fp8 の 2 variant を出しており、turbo は tools / response_format / structured_outputs
# を非対応のため、tool_choice="required" や JSON mode 経路が即座に壊れる。
# 実験 mid-run の事故を防ぐため、provider を明示的に固定する。
_ENV_VAR_OPENROUTER_PROVIDER = "OPENROUTER_PROVIDER"
_ENV_VAR_OPENROUTER_QUANTIZATION = "OPENROUTER_QUANTIZATION"
_ENV_VAR_OPENROUTER_REQUIRE_PARAMS = "OPENROUTER_REQUIRE_PARAMS"
_TRUTHY_ENV_VALUES = frozenset({"1", "true", "yes", "on"})


def _resolve_openrouter_routing_from_env() -> Optional[Dict[str, Any]]:
    """OpenRouter provider routing 設定を env から resolve し ``extra_body`` 用 dict を返す。

    いずれの env も未設定なら ``None`` を返す (= 何も注入しない / 既存挙動)。
    1 つでも設定があれば ``{"provider": {...}}`` を返す。

    ``OPENROUTER_PROVIDER`` が設定された場合は ``allow_fallbacks=False`` を必ず付ける
    (provider 固定の意図を裏切らないため)。

    返り値は **immutable 想定** で扱うこと (constructor で 1 度作って共有)。
    """
    provider = (os.environ.get(_ENV_VAR_OPENROUTER_PROVIDER) or "").strip()
    quantization = (os.environ.get(_ENV_VAR_OPENROUTER_QUANTIZATION) or "").strip()
    require_params_raw = (os.environ.get(_ENV_VAR_OPENROUTER_REQUIRE_PARAMS) or "").strip().lower()
    require_params = require_params_raw in _TRUTHY_ENV_VALUES
    if not provider and not quantization and not require_params:
        return None
    block: Dict[str, Any] = {}
    if provider:
        block["order"] = [provider]
        block["allow_fallbacks"] = False
    if quantization:
        block["quantizations"] = [quantization]
    if require_params:
        block["require_parameters"] = True
    return {"provider": block}


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
    ISemanticGistCompletionPort,
    IShortTermMemorySummaryCompletionPort,
    IShortTermMemoryLongSummaryCompletionPort,
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

        # OpenRouter provider routing: constructor 時点で env を 1 度だけ resolve
        # して保持する。invoke() / complete_*_json() の度に env を読み直すと、実験
        # 中の env 変動で挙動がブレるため。
        self._openrouter_routing: Optional[Dict[str, Any]] = _resolve_openrouter_routing_from_env()

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
        """ツール無しの chat completion 用（Episode Encoder 等）。カスタム base 無しでは api_key が必須。

        OpenRouter provider routing env が設定されている場合、``extra_body`` を
        自動付与する (provider / quantization の固定)。
        """
        self._assert_can_call_litellm()
        base: Dict[str, Any] = {"model": self._model, "api_key": self._lite_api_key()}
        if self._api_base is not None:
            base["api_base"] = self._api_base
        if self._openrouter_routing is not None:
            base["extra_body"] = dict(self._openrouter_routing)
        return base

    @property
    def openrouter_routing(self) -> Optional[Dict[str, Any]]:
        """現在 inject される OpenRouter routing を返す (実験 trace 等の観測用)。"""
        if self._openrouter_routing is None:
            return None
        return copy.deepcopy(self._openrouter_routing)

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
            if self._openrouter_routing is not None:
                completion_kw["extra_body"] = copy.deepcopy(self._openrouter_routing)
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
        prompt_tokens, completion_tokens, cached_tokens = self._extract_token_usage(response)
        tool_call = self._parse_tool_call(response, messages, tools)
        self._emit_metrics(
            metrics_sink,
            wall_latency_ms=wall_latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            success=tool_call is not None,
            error_code=None if tool_call is not None else "NO_TOOL_CALL",
        )
        return tool_call

    @staticmethod
    def _extract_token_usage(response: Any) -> tuple[int, int, int]:
        """litellm レスポンスから (prompt_tokens, completion_tokens, cached_tokens) を取得する。

        provider 差で usage の形が違うので best-effort で各経路を試す。欠落時は 0。

        - vLLM / OpenAI: ``usage.prompt_tokens_details.cached_tokens``
        - Anthropic: ``usage.cache_read_input_tokens``
        - vLLM 旧版や一部 OpenAI 互換サーバ: ``usage.cached_tokens`` 直下

        cached_tokens は prompt_tokens に内包される (合計ではなく内訳)。
        prefix cache 効率の指標として実験 #356 後続で利用する。
        """
        try:
            usage = getattr(response, "usage", None)
            if usage is None:
                return 0, 0, 0
            prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
            completion = int(getattr(usage, "completion_tokens", 0) or 0)
            cached = LiteLLMClient._extract_cached_tokens(usage)
            return prompt, completion, cached
        except Exception:
            return 0, 0, 0

    @staticmethod
    def _extract_cached_tokens(usage: Any) -> int:
        """usage オブジェクトから cached_tokens を best-effort で取り出す。

        OpenAI / vLLM 系の ``prompt_tokens_details.cached_tokens`` を最優先し、
        次に Anthropic の ``cache_read_input_tokens``、最後に旧 vLLM の直下
        ``cached_tokens`` を見る。どれも取れなければ 0。
        """
        details = getattr(usage, "prompt_tokens_details", None)
        if details is not None:
            # litellm は dict / object どちらでも返してくることがあるので両対応
            if isinstance(details, dict):
                v = details.get("cached_tokens")
            else:
                v = getattr(details, "cached_tokens", None)
            if v is not None:
                try:
                    return int(v)
                except (TypeError, ValueError):
                    pass
        anthropic_cached = getattr(usage, "cache_read_input_tokens", None)
        if anthropic_cached is not None:
            try:
                return int(anthropic_cached)
            except (TypeError, ValueError):
                pass
        legacy = getattr(usage, "cached_tokens", None)
        if legacy is not None:
            try:
                return int(legacy)
            except (TypeError, ValueError):
                pass
        return 0

    def _emit_metrics(
        self,
        sink: Optional[LlmCallMetricsSink],
        *,
        wall_latency_ms: int,
        prompt_tokens: int,
        completion_tokens: int,
        success: bool,
        error_code: Optional[str],
        cached_tokens: int = 0,
    ) -> None:
        if sink is None:
            return
        try:
            metrics = LlmCallMetrics(
                model=self._model,
                wall_latency_ms=wall_latency_ms,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached_tokens=cached_tokens,
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

        注意 (PR #358): 本 API は episodic subjective rewrite 専用のため metrics は
        収集しない。τ_sim 分析対象は Phase A の意思決定 LLM のみ。subjective 系の
        metrics が必要になったら専用の sink 引数を足すこと (現状の実験 #356 では不要)。
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

    def complete_semantic_gist_json(
        self,
        messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """tools 無しで semantic gist JSON object を返す (Phase 1b)。

        ``complete_episode_subjective_json`` と同じ json_object 強制完了を
        使う (LLM 側から見れば同じ呼び出し)。失敗ハンドリングも共通。
        """
        return self.complete_episode_subjective_json(messages)

    def complete_short_term_summary_json(
        self,
        messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """tools 無しで L4 mid summary JSON object を返す (Phase 2)。

        既存の json_object 強制完了をそのまま使う (LLM 側から見れば同じ呼出)。
        prompt 構築や parse は ``ShortTermMemorySummaryService`` 側の責務。
        """
        return self.complete_episode_subjective_json(messages)

    def complete_short_term_long_summary_json(
        self,
        messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """tools 無しで L5 long summary JSON object を返す (Phase 3)。

        既存の json_object 強制完了をそのまま使う (LLM 側から見れば同じ呼出)。
        prompt 構築や parse は ``ShortTermMemoryLongSummaryService`` 側の責務。
        """
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
