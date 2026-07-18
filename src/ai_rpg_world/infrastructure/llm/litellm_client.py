"""
LiteLLM を用いた ILLMClient 実装。

API Key: コンストラクタで api_key を渡さない場合は環境変数 OPENAI_API_KEY を参照する。
api_key 未指定時は .env を自動で読み込み、その後に環境変数を参照する。
.env は .gitignore に含めること。

OpenAI 互換エンドポイント（SSH 越しの vLLM 等）: ``OPENAI_API_BASE`` に
``http://127.0.0.1:8000/v1`` のようなベース URL を設定する。
その場合 OPENAI_API_KEY が空でも ``EMPTY`` を送り続行する（vLLM 既定の無認証構成向け）。
"""

import concurrent.futures
import json
import logging
import copy
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional

import litellm
from litellm import AuthenticationError as LitellmAuthenticationError
from litellm import InternalServerError as LitellmInternalServerError
from litellm import RateLimitError as LitellmRateLimitError
from litellm import ServiceUnavailableError as LitellmServiceUnavailableError

from ai_rpg_world.application.llm.ports.episodic_chunk_subjective_completion_port import (
    IEpisodicChunkSubjectiveCompletionPort,
)
from ai_rpg_world.application.llm.ports.belief_consolidation_completion_port import (
    IBeliefConsolidationCompletionPort,
)
from ai_rpg_world.application.llm.ports.episodic_reinterpretation_completion_port import (
    IEpisodicReinterpretationCompletionPort,
)
from ai_rpg_world.application.llm.ports.llm_client_port import ILLMClient
from ai_rpg_world.application.llm.ports.semantic_gist_completion_port import (
    ISemanticGistCompletionPort,
)
from ai_rpg_world.application.llm.ports.short_term_memory_completion_ports import (
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

# PR #444: litellm 既定の request_timeout=6000 (= 100 分) は long-tail hang を
# silent に許容し、1 件の slow call が実験全体を 38 分に引き延ばす silent
# failure を引き起こしていた (PR #443 で 303 秒の outlier を発見)。
# 実験 / 本番ともに 60-120 秒で打ち切る方が観測上ノイズが少ない (= 同 LLM call
# は通常 1-5 秒)。env override 可能。
_ENV_VAR_LLM_TIMEOUT = "LLM_REQUEST_TIMEOUT_SECONDS"
_DEFAULT_LLM_TIMEOUT_SECONDS = 90.0

# Wall-time hard cap (PR #463 後続: H run で 122s outlier を観測した対策)。
#
# 背景: litellm に渡した `timeout=90` (float) は httpx で
# `Timeout(connect=90, read=90, write=90, pool=90)` に展開される。read=90 は
# 「1 回の socket.recv 待ち上限」であり total wall-time ではない。
# OpenRouter が backend hang 中に TCP keep-alive ack / partial chunk / proxy
# heartbeat を時々返すと read timer がリセットされ、結果 122s 等まで延びる。
#
# 対策: アプリ層で `concurrent.futures.ThreadPoolExecutor.result(timeout=)`
# を使い **wall-time の hard cap** を独立に強制する。litellm が何秒待つかに
# 依存せず、確実に N 秒で打ち切る。
#
# default: self._timeout_seconds + 5.0 (= 95s) → 通常 timeout より少しだけ
# 余裕を持たせ、httpx 経路が正常に効いた場合の例外伝播を優先する。
# 実験で「全体の律速を避けたい」用途では env で短く (例 45) してよい:
# 通常 p99 ≈ 30-40s なので 45s なら正常 call はほぼ通る + outlier だけ切れる。
_ENV_VAR_LLM_WALL_CAP = "LLM_WALL_TIME_CAP_SECONDS"
_DEFAULT_WALL_CAP_BUFFER_SECONDS = 5.0

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

# Reasoning effort 制御 (deepseek-v4-flash 等の reasoning model 対策)。
#
# 背景: deepseek-v4-flash は reasoning model で、default で `effort: "high"` が
# 乗り、output token を 5-15× 膨らませて latency / cost を爆発させる (我々の
# agent turn では reasoning は不要、確定 tool_call が欲しいだけ)。
#
# litellm 1.44 の OpenrouterConfig は `reasoning_effort` を素通しせず、
# DeepSeekChatConfig は `thinking: {type: enabled}` に強制 collapse する
# (issues #27439 / #27453)。そのため top-level `reasoning_effort=` は信頼でき
# ない。
#
# 解決: ``extra_body`` に **OpenRouter 統一 envelope** (`reasoning`) と
# **DeepSeek native kill switch** (`thinking`) を **両方** inject する
# (belt-and-suspenders)。どちらが provider passthrough されても効くように。
#
# 値:
# - `"none"` (default) = reasoning 完全 OFF
# - `"minimal"` = 最小 budget で reasoning (~10% of max_tokens)
# - `"low"` / `"medium"` / `"high"` / `"xhigh"` = OpenRouter 標準段階
# - 空文字 = inject しない (= reasoning フィールド一切付けない / 古い model 互換)
#
# 非 reasoning model に対しても付与可だが、provider 側で無視されるはず
# (OpenAI 経由でも unknown field は silently dropped)。
_ENV_VAR_REASONING_EFFORT = "LLM_REASONING_EFFORT"
_DEFAULT_REASONING_EFFORT = "none"  # reasoning OFF が agent turn 用途の安全 default

# ``_build_extra_body`` の reasoning override 用 sentinel。「override 指定なし
# (= 構築時の既定を使う)」と「override として None (= reasoning を inject しない)」
# を区別するために object() を使う。
_NO_REASONING_OVERRIDE = object()
_VALID_REASONING_EFFORTS = frozenset({
    "",          # 何も inject しない (旧 model 互換)
    "none",      # 明示 OFF
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
})

# 選択的リトライ (PR #X): max_retries=0 (litellm/openai SDK の透過リトライ無効化) を
# 維持しつつ、本クラスのアプリ層で「特定の一時失敗」だけを手動 backoff で retry する。
#
# なぜ「全 retry を SDK に任せない」か:
# - SDK の retry は httpx.TimeoutException でも回り、timeout=90s 設定下でも
#   wall_time が 222s まで膨らむ outlier を発生させた (#454 で fix)
# - 一方で 429 (rate limit) や 5xx (一時サーバエラー) の retry は agent turn の
#   成功率に直結する。ここを切ると単発失敗が連鎖して run が空回りする
#
# 解決: SDK の透過 retry は完全に切り (max_retries=0)、アプリ層で
# RateLimitError / InternalServerError / ServiceUnavailableError のみを catch
# して短い backoff で N 回 retry する。timeout / 認証エラー / BadRequest 等は
# retry しない (= 即失敗で turn_runner レベルに上げる)。
_ENV_VAR_RATE_LIMIT_RETRY_ATTEMPTS = "LLM_RATE_LIMIT_RETRY_ATTEMPTS"
_ENV_VAR_RATE_LIMIT_RETRY_BASE_SLEEP = "LLM_RATE_LIMIT_RETRY_BASE_SLEEP"
_DEFAULT_RATE_LIMIT_RETRY_ATTEMPTS = 3       # 1 回目失敗後、最大 3 回再試行
_DEFAULT_RATE_LIMIT_RETRY_BASE_SLEEP = 2.0   # 2s → 4s → 8s (exponential)
_RATE_LIMIT_RETRY_MAX_SLEEP = 30.0           # 1 回あたりの上限 (秒)


def _is_retryable_transient_error(exc: BaseException) -> bool:
    """RateLimit / 一時 5xx のような「待てば直る」例外かを判定する。

    timeout / auth / bad_request は対象外。前者は SDK 透過 retry で延長して
    しまうので「即失敗」が正しい (turn_runner で次ターンに recover)。
    後者 2 つはリトライしても直らない。
    """
    return isinstance(
        exc,
        (LitellmRateLimitError, LitellmInternalServerError, LitellmServiceUnavailableError),
    )


def _detect_openrouter_base(api_base: Optional[str]) -> bool:
    """``api_base`` が OpenRouter のものか判定する。

    OpenRouter 経由のときだけ ``extra_body.usage.include=True`` を付けて cost を
    返してもらう。判定は素朴に「openrouter.ai を含む」かどうかだけで十分 (誤判定の
    最悪ケースでも extra_body に余計な field が付くだけで、OpenAI / vLLM は無視する
    ことが多いが、念のため避ける)。
    """
    if not api_base:
        return False
    return "openrouter.ai" in api_base.lower()


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


def _validate_reasoning_effort(
    effort: str, *, source_label: str = "reasoning_effort"
) -> str:
    """effort 文字列を正規化し、未知値は ValueError で弾く (silent fallback 防止)。

    ``source_label`` はエラーメッセージ中の変数名 (env 経路では ``LLM_REASONING_EFFORT``、
    invoke の per-call override では ``reasoning_effort``) を切り替えるためのもの。
    """
    normalized = effort.strip().lower()
    if normalized not in _VALID_REASONING_EFFORTS:
        raise ValueError(
            f"{source_label}={effort!r} is not recognized. "
            f"valid: {sorted(_VALID_REASONING_EFFORTS)}"
        )
    return normalized


def _build_reasoning_block(effort: str) -> Optional[Dict[str, Any]]:
    """検証済みの ``effort`` から ``extra_body`` 用の reasoning ブロックを組む。

    - ``""`` → ``None`` (= reasoning 系 field を一切 inject しない。古い model 互換)
    - ``"none"`` 〜 ``"xhigh"`` → OpenRouter ``reasoning`` envelope と DeepSeek
      native ``thinking`` の両方を返す (belt-and-suspenders)

    env 経路 (`_resolve_reasoning_effort_from_env`) と invoke の per-call override の
    両方が本関数を共有し、reasoning ブロックの形を 1 箇所に集約する。
    """
    if effort == "":
        return None
    block: Dict[str, Any] = {
        # OpenRouter 統一 envelope (primary control path)
        "reasoning": {
            "effort": effort,
            # exclude=True で response から reasoning token 本文を剥がす (= prompt
            # cache hit / cost 計測の安定化。なお tool-calling 経路では本文は
            # どのみち返らず、reasoning_token 数だけ usage に残る)
            "exclude": True,
        },
    }
    if effort == "none":
        # DeepSeek API native kill switch。OpenRouter が provider passthrough
        # するときに reasoning envelope を読み落とすケースの保険
        block["thinking"] = {"type": "disabled"}
    return block


def _resolve_reasoning_effort_from_env() -> Optional[Dict[str, Any]]:
    """``LLM_REASONING_EFFORT`` env を解決し、``extra_body`` 用の reasoning ブロックを返す。

    - 未設定 → default の ``"none"`` (= 完全 OFF) として扱う
    - 空文字 ``""`` (明示) → ``None`` (reasoning 系 field を一切 inject しない)
    - ``"none"`` 〜 ``"xhigh"`` → reasoning + thinking ブロック
    - 未知文字列 → ValueError (silent fallback 防止 / PR #433 経緯と同じ方針)
    """
    raw_env = os.environ.get(_ENV_VAR_REASONING_EFFORT)
    effort = _DEFAULT_REASONING_EFFORT if raw_env is None else raw_env
    return _build_reasoning_block(
        _validate_reasoning_effort(effort, source_label=_ENV_VAR_REASONING_EFFORT)
    )


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
    IBeliefConsolidationCompletionPort,
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
        timeout_seconds: Optional[float] = None,
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

        # PR #444: timeout を明示。引数 > env > default の優先で解決し、毎呼び
        # 出しの litellm.completion に渡す。これがないと litellm 既定 6000 秒
        # (= 100 分) で長期 hang を許容してしまう。
        if timeout_seconds is not None:
            self._timeout_seconds: float = float(timeout_seconds)
        else:
            raw = (os.environ.get(_ENV_VAR_LLM_TIMEOUT) or "").strip()
            if raw:
                try:
                    self._timeout_seconds = float(raw)
                except ValueError:
                    raise ValueError(
                        f"{_ENV_VAR_LLM_TIMEOUT}={raw!r} must be a number (seconds)"
                    )
            else:
                self._timeout_seconds = _DEFAULT_LLM_TIMEOUT_SECONDS

        # OpenRouter provider routing: constructor 時点で env を 1 度だけ resolve
        # して保持する。invoke() / complete_*_json() の度に env を読み直すと、実験
        # 中の env 変動で挙動がブレるため。
        self._openrouter_routing: Optional[Dict[str, Any]] = _resolve_openrouter_routing_from_env()

        # reasoning model (deepseek-v4-flash 等) に対する effort 制御。
        # default = "none" (= reasoning 完全 OFF)。LLM_REASONING_EFFORT で上書き可能。
        # 非 reasoning model でも余計な field が乗るだけで害はない (= provider 側で
        # silently dropped)。
        self._reasoning_block: Optional[Dict[str, Any]] = _resolve_reasoning_effort_from_env()

        # OpenRouter は api_base が openrouter ドメインかで判定する。
        # ``extra_body.usage.include=True`` を付けると response.usage.cost に
        # USD コストを乗せて返してくれる (per-call cost を計測したい)。
        # OpenAI 直結 / vLLM には影響しない (api_base が違うので付かない)。
        self._is_openrouter_base: bool = _detect_openrouter_base(self._api_base)

        # 選択的リトライの設定。env override 可能 (実験再現性)。
        self._rate_limit_retry_attempts: int = self._resolve_int_env(
            _ENV_VAR_RATE_LIMIT_RETRY_ATTEMPTS,
            _DEFAULT_RATE_LIMIT_RETRY_ATTEMPTS,
            minimum=0,
        )
        self._rate_limit_retry_base_sleep: float = self._resolve_float_env(
            _ENV_VAR_RATE_LIMIT_RETRY_BASE_SLEEP,
            _DEFAULT_RATE_LIMIT_RETRY_BASE_SLEEP,
            minimum=0.0,
        )

        # Wall-time hard cap: httpx の per-recv read timeout が効かないケースの
        # 保険として、`concurrent.futures.ThreadPoolExecutor.result(timeout=)`
        # で wall-time を独立に強制する。default は self._timeout_seconds + 5s
        # (httpx 経路が正常に動くケースの邪魔をしない)。env で短く設定すれば
        # 「全体の律速を避ける」用途に使える (= 通常 p99 < 40s なので 45s 等
        # 短めでも正常 call はほぼ通る + outlier だけ確実に切れる)。
        env_cap = (os.environ.get(_ENV_VAR_LLM_WALL_CAP) or "").strip()
        if env_cap:
            try:
                self._wall_cap_seconds: float = float(env_cap)
            except ValueError:
                raise ValueError(
                    f"{_ENV_VAR_LLM_WALL_CAP}={env_cap!r} must be a number (seconds)"
                )
            if self._wall_cap_seconds <= 0:
                raise ValueError(
                    f"{_ENV_VAR_LLM_WALL_CAP}={self._wall_cap_seconds} must be > 0"
                )
        else:
            self._wall_cap_seconds = (
                self._timeout_seconds + _DEFAULT_WALL_CAP_BUFFER_SECONDS
            )

        self._logger = logging.getLogger(self.__class__.__name__)

    @staticmethod
    def _resolve_int_env(name: str, default: int, *, minimum: int) -> int:
        raw = (os.environ.get(name) or "").strip()
        if not raw:
            return default
        try:
            value = int(raw)
        except ValueError:
            raise ValueError(f"{name}={raw!r} must be an integer")
        if value < minimum:
            raise ValueError(f"{name}={value} must be >= {minimum}")
        return value

    @staticmethod
    def _resolve_float_env(name: str, default: float, *, minimum: float) -> float:
        raw = (os.environ.get(name) or "").strip()
        if not raw:
            return default
        try:
            value = float(raw)
        except ValueError:
            raise ValueError(f"{name}={raw!r} must be a number")
        if value < minimum:
            raise ValueError(f"{name}={value} must be >= {minimum}")
        return value

    def _call_with_wall_cap(self, call_fn: Callable[[], Any]) -> Any:
        """``self._wall_cap_seconds`` を per-attempt wall-time hard cap として強制する。

        ``concurrent.futures.ThreadPoolExecutor.result(timeout=)`` で wall-time を
        独立に計測し、上限超過時は ``litellm.Timeout`` を投げる
        (= selective_retry の retry 対象外として扱われ、turn_runner レベルで
        recover される)。

        なぜ wall cap を per-attempt にするか:
        - per-total (全 retry 合算) にすると、retry sleep (2/4/8s) が cap を
          食い潰して 1 attempt も成立しないケースが出る
        - per-attempt なら正常 call は影響を受けず、outlier だけ確実に切れる
        - ユーザー希望「全体の律速を避ける」を満たす最短距離

        なぜ ThreadPoolExecutor を毎回 new するか:
        - max_workers=1 + with 文で確実に shutdown され、daemon thread を放置
          しない
        - per-call の executor 作成 overhead は microsec オーダーで無視できる
        - 共有 executor を持つと shutdown 責務 / リーク管理が複雑化する
        """
        # litellm.Timeout を遅延 import (テストで mock しやすいように、
        # クラスレベルでなくここで取得する)
        try:
            from litellm import Timeout as LitellmTimeout  # type: ignore
        except ImportError:  # pragma: no cover
            LitellmTimeout = Exception  # type: ignore

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(call_fn)
            try:
                return fut.result(timeout=self._wall_cap_seconds)
            except concurrent.futures.TimeoutError:
                # 下位 socket は GC で閉じる。Future はキャンセル試行のみ
                # (LLM call は止まらないが、メインスレッドはここで進める)
                fut.cancel()
                raise LitellmTimeout(
                    message=(
                        f"LLM call exceeded wall-time cap "
                        f"{self._wall_cap_seconds:.1f}s "
                        f"({_ENV_VAR_LLM_WALL_CAP} で調整可)"
                    ),
                    model=self._model,
                    llm_provider="litellm_client",
                )

    def _call_with_selective_retry(self, call_fn):
        """RateLimit / 一時 5xx のみ手動 backoff で retry し、それ以外は即 raise。

        各 attempt は ``_call_with_wall_cap`` で wall-time 上限を強制される。

        SDK の透過 retry を無効化 (max_retries=0) しているため、ここで補う。
        timeout / auth / bad_request は retry しない:
        - timeout: SDK retry で wall_time が 3 倍に膨らむ outlier の原因 (#454)。
          turn_runner レベルの「次ターンで再試行」に任せる
        - auth: retry しても直らない
        - bad_request: payload が壊れているので retry しても直らない

        backoff: base * 2^attempt (cap _RATE_LIMIT_RETRY_MAX_SLEEP)。jitter は
        意図的に入れない (1 client の retry が他 client と衝突する状況は想定外
        で、ここでは入れると実験再現性が下がるだけ)。
        """
        last_exc: Optional[BaseException] = None
        for attempt in range(self._rate_limit_retry_attempts + 1):
            try:
                return self._call_with_wall_cap(call_fn)
            except Exception as exc:
                if not _is_retryable_transient_error(exc):
                    raise
                last_exc = exc
                if attempt >= self._rate_limit_retry_attempts:
                    break
                sleep_for = min(
                    self._rate_limit_retry_base_sleep * (2 ** attempt),
                    _RATE_LIMIT_RETRY_MAX_SLEEP,
                )
                self._logger.warning(
                    "Retryable LLM error (%s) attempt=%d/%d, sleeping %.1fs: %s",
                    type(exc).__name__,
                    attempt + 1,
                    self._rate_limit_retry_attempts,
                    sleep_for,
                    exc,
                )
                time.sleep(sleep_for)
        assert last_exc is not None
        raise last_exc

    def _build_extra_body(
        self, reasoning_override: Any = _NO_REASONING_OVERRIDE
    ) -> Optional[Dict[str, Any]]:
        """litellm.completion に渡す ``extra_body`` を組み立てる。

        - provider routing (OPENROUTER_PROVIDER 等の env が設定されているとき)
        - usage.include (api_base が OpenRouter のとき、cost を返してもらう)
        - reasoning + thinking (reasoning model 用、default OFF)

        ``reasoning_override`` に何か渡された場合 (sentinel 以外)、構築時の既定
        ``self._reasoning_block`` の代わりにその値を使う (``None`` を渡せば「この
        呼び出しは reasoning を一切 inject しない」を意味する)。案A の per-call
        band-gated thinking がここを通る。

        どれも要らないときは None を返す (= extra_body を一切渡さない)。
        """
        block: Dict[str, Any] = {}
        if self._openrouter_routing is not None:
            block.update(copy.deepcopy(self._openrouter_routing))
        if self._is_openrouter_base:
            block["usage"] = {"include": True}
        reasoning = (
            self._reasoning_block
            if reasoning_override is _NO_REASONING_OVERRIDE
            else reasoning_override
        )
        if reasoning is not None:
            block.update(copy.deepcopy(reasoning))
        return block or None

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
        自動付与する (provider / quantization の固定)。さらに api_base が
        OpenRouter なら ``usage.include=True`` も同 ``extra_body`` に乗せて cost
        を返してもらう。
        """
        self._assert_can_call_litellm()
        base: Dict[str, Any] = {
            "model": self._model,
            "api_key": self._lite_api_key(),
            # PR #444: 長期 hang を必ず打ち切る (default 90s / env override 可)
            "timeout": self._timeout_seconds,
            # litellm 1.44 + OpenAI SDK 1.x の合成挙動として、max_retries 未指定だと
            # openai.DEFAULT_MAX_RETRIES=2 が黙って注入され、httpx.TimeoutException
            # 発生時に exponential backoff (INITIAL=0.5s, MAX=8s) で 2 回 retry する。
            # 結果として timeout=90s 設定でも wall_time が 90 + 90 + 成功時間 ≈ 220s+
            # まで膨らむ outlier が観測された (C run v3: 222s/164s/130s)。
            # ここで明示的に 0 を渡し、wall_time 上限を実効的に self._timeout_seconds に固定する。
            "max_retries": 0,
        }
        if self._api_base is not None:
            base["api_base"] = self._api_base
        extra_body = self._build_extra_body()
        if extra_body is not None:
            base["extra_body"] = extra_body
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
        reasoning_effort: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        1 回の LLM 呼び出しを行い、tool_call があれば {"name": str, "arguments": dict} を返す。
        tool_call が無い場合やパースに失敗した場合は None を返す。
        API エラー時は LlmApiCallException を投げる。

        ``metrics_sink`` が渡された場合、呼び出し成否によらず ``LlmCallMetrics`` を 1 件
        sink に流す (実験 #356: τ_sim 設定根拠 + scenario cost 評価用)。

        ``reasoning_effort`` を渡すと、その 1 呼び出しだけ構築時の既定 (env) を
        上書きして reasoning の effort を変える (案A: band-gated thinking)。``None``
        なら既定のまま (既存挙動)。未知値は ``ValueError``。tool-calling 経路では
        reasoning 本文は返らないが、reasoning_token 数は usage 経由で metrics に載る。
        """
        self._assert_can_call_litellm()
        if reasoning_effort is None:
            reasoning_override: Any = _NO_REASONING_OVERRIDE
        else:
            reasoning_override = _build_reasoning_block(
                _validate_reasoning_effort(reasoning_effort)
            )
        start_monotonic = time.monotonic()
        try:
            completion_kw: Dict[str, Any] = {
                "model": self._model,
                "messages": messages,
                "tools": tools,
                "tool_choice": tool_choice,
                "api_key": self._lite_api_key(),
                # PR #444: 長期 hang を必ず打ち切る
                "timeout": self._timeout_seconds,
                # max_retries=0: OpenAI SDK の default 2 回 retry + exponential backoff
                # で wall_time が timeout の 3 倍まで膨らむ outlier を防ぐ。
                # 詳細は completion_base_kwargs() 内のコメントを参照。
                "max_retries": 0,
            }
            if self._api_base is not None:
                completion_kw["api_base"] = self._api_base
            extra_body = self._build_extra_body(reasoning_override=reasoning_override)
            if extra_body is not None:
                completion_kw["extra_body"] = extra_body
            # SDK 透過 retry は max_retries=0 で無効化済み。RateLimit / 一時 5xx の
            # みアプリ層で短い backoff retry する。
            response = self._call_with_selective_retry(
                lambda: litellm.completion(**completion_kw)
            )
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
        reasoning_tokens = self._extract_reasoning_tokens(response)
        cost_usd = self._extract_cost_usd(response)
        tool_call = self._parse_tool_call(response, messages, tools)
        self._emit_metrics(
            metrics_sink,
            wall_latency_ms=wall_latency_ms,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            reasoning_tokens=reasoning_tokens,
            cost_usd=cost_usd,
            success=tool_call is not None,
            error_code=None if tool_call is not None else "NO_TOOL_CALL",
        )
        return tool_call

    @staticmethod
    def _extract_reasoning_tokens(response: Any) -> int:
        """litellm レスポンスの ``usage.completion_tokens_details.reasoning_tokens`` を
        best-effort で取り出す。reasoning model が思考に使ったトークン数。

        tool-calling 経路では reasoning 本文は返らないが、このトークン数は usage に
        残るので「実際に何回・どれだけ熟考したか」の観測点になる (案A の trace 用)。
        取れない provider では 0 に縮退する (例外を投げない)。
        """
        try:
            usage = getattr(response, "usage", None)
            if usage is None:
                return 0
            details = getattr(usage, "completion_tokens_details", None)
            if details is None:
                return 0
            if isinstance(details, dict):
                v = details.get("reasoning_tokens")
            else:
                v = getattr(details, "reasoning_tokens", None)
            return int(v) if v is not None else 0
        except (TypeError, ValueError):
            return 0

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
        reasoning_tokens: int = 0,
        cost_usd: float = 0.0,
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
                reasoning_tokens=reasoning_tokens,
                tps=LlmCallMetrics.compute_tps(completion_tokens, wall_latency_ms),
                success=success,
                error_code=error_code,
                cost_usd=cost_usd,
            )
            sink.record(metrics)
        except Exception:
            # メトリクス記録の失敗が LLM 呼び出し本体の挙動を倒さないよう吸収。
            self._logger.exception("metrics_sink.record failed")

    @staticmethod
    def _extract_cost_usd(response: Any) -> float:
        """litellm レスポンスから 1 call 分の USD コストを抜く (provider 宣告値)。

        OpenRouter は ``extra_body.usage.include=True`` を付けた場合、
        ``response.usage.cost`` (USD) を返す。OpenAI 直結 / vLLM 等は返さないので
        0.0。litellm が dict / pydantic model のどちらで持つかは provider 経路で
        揺れるため両方拾う。
        """
        try:
            usage = getattr(response, "usage", None)
            if usage is None:
                return 0.0
            # pydantic-like (attribute) アクセス
            cost = getattr(usage, "cost", None)
            if cost is None and isinstance(usage, dict):
                # 一部 provider で dict のまま戻る場合
                cost = usage.get("cost")
            if cost is None:
                return 0.0
            return float(cost)
        except (TypeError, ValueError):
            return 0.0

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
            # SDK 透過 retry は max_retries=0 で無効化済み。RateLimit / 一時 5xx の
            # みアプリ層で短い backoff retry する。
            response = self._call_with_selective_retry(
                lambda: litellm.completion(
                    messages=messages,
                    response_format={"type": "json_object"},
                    **kwargs,
                )
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

    def complete_belief_consolidation_json(
        self,
        messages: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """tools 無しで固着パス (belief journal 統合) の decisions JSON を返す (U3b)。

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
