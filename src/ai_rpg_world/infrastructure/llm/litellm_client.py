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
import copy
import json
import logging
import os
import re
import time
from collections.abc import Callable, Mapping
from typing import Any, TypeVar

import litellm
from litellm import AuthenticationError as LitellmAuthenticationError
from litellm import InternalServerError as LitellmInternalServerError
from litellm import RateLimitError as LitellmRateLimitError
from litellm import ServiceUnavailableError as LitellmServiceUnavailableError

from ai_rpg_world.application.llm.contracts.aux_llm_call import (
    AuxLlmCall,
    AuxLlmCallSink,
    AuxLlmComponent,
)
from ai_rpg_world.application.llm.contracts.llm_call_metrics import (
    LlmCallMetrics,
    LlmCallMetricsSink,
)
from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.application.llm.ports.episodic_chunk_subjective_completion_port import (
    IEpisodicChunkSubjectiveCompletionPort,
)
from ai_rpg_world.application.llm.ports.llm_client_port import ILLMClient, ToolChoice
from ai_rpg_world.application.llm.ports.short_term_memory_completion_ports import (
    IShortTermMemoryLongSummaryCompletionPort,
    IShortTermMemorySummaryCompletionPort,
)
from ai_rpg_world.being.application.episode_writing import EpisodeWritingCompletion

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

# 失敗時に metrics/trace に残す例外本文の最大文字数。provider 400 の本文
# (provider 名・provider エラーコード等) が診断に足りる長さを確保しつつ、
# trace.jsonl が膨れないよう truncate する。
_ERROR_DETAIL_MAX_CHARS = 500

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

# Reasoning effort 制御 (deepseek-v4-flash 等の reasoning model 対策)。
#
# 背景: deepseek-v4-flash は reasoning model で、default で `effort: "high"` が
# 乗り、output token を 5-15× 膨らませて latency / cost を爆発させる (我々の
# agent turn では reasoning は不要、確定 tool_call が欲しいだけ)。
#
# reasoning を止める ``none`` では OpenRouter 統一 envelope と DeepSeek native
# kill switch を併用する。reasoning を有効にするときも OpenRouter 統一 envelope
# (``extra_body`` の ``reasoning.effort``) で渡し、無効化 field を同時に送らない。
# litellm の top-level ``reasoning_effort`` は、litellm のモデル表で reasoning 対応と
# 確かめられないモデルを送る前に弾くため使わない (design_decisions D1582)。
#
# 値:
# - `"none"` (default) = reasoning 完全 OFF
# - `"minimal"` = 最小 budget で reasoning (~10% of max_tokens)
# - `"low"` / `"medium"` / `"high"` / `"xhigh"` = OpenRouter 標準段階
# - 空文字 = inject しない (= reasoning フィールド一切付けない / 古い model 互換)
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


def _detect_openrouter_base(api_base: str | None) -> bool:
    """``api_base`` が OpenRouter のものか判定する。

    OpenRouter 経由のときだけ ``extra_body.usage.include=True`` を付けて cost を
    返してもらう。判定は素朴に「openrouter.ai を含む」かどうかだけで十分 (誤判定の
    最悪ケースでも extra_body に余計な field が付くだけで、OpenAI / vLLM は無視する
    ことが多いが、念のため避ける)。
    """
    if not api_base:
        return False
    return "openrouter.ai" in api_base.lower()


# runtime_config に `"OPENROUTER_PROVIDER": "DeepInfra"`、`"OPENROUTER_QUANTIZATION": "fp8"`
# を書くと、全 litellm.completion 呼び出しに `extra_body.provider.{only, quantizations,
# require_parameters}` を注入する。
# OpenRouter docs: https://openrouter.ai/docs/provider-routing
#
# なぜ必要か: api_base=https://openrouter.ai/api/v1 で叩くと OpenRouter が
# provider を自由に選ぶ。例えば Gemma 4 31B では DeepInfra が turbo (fp4) /
# fp8 の 2 variant を出しており、turbo は tools / response_format / structured_outputs
# を非対応のため、tool_choice="required" や JSON mode 経路が即座に壊れる。
# 実験 mid-run の事故を防ぐため、provider を明示的に固定する。
def _build_openrouter_routing(
    *,
    provider: str | None,
    quantization: str | None,
) -> dict[str, Any] | None:
    """明示値から OpenRouter provider routing 設定を組む。"""
    provider = (provider or "").strip()
    quantization = (quantization or "").strip()
    if not provider and not quantization:
        return None
    block: dict[str, Any] = {}
    if provider:
        # ``order`` は希望順位であり、Cloudflare のように指定先だけへ固定したい
        # 場合に解決されないことがある。``only`` なら 1 社固定の意味が明示的で、
        # 別 provider へ静かに流れる余地もない。
        block["only"] = [provider]
    if quantization:
        block["quantizations"] = [quantization]
    # tool_choice="required" を受け付けない provider へ黙って流さず、OpenRouter に
    # 送る前に止めさせる (design_decisions D1631-2)。
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


def _build_reasoning_block(effort: str) -> dict[str, Any] | None:
    """検証済みの ``effort`` から ``extra_body`` に載せる reasoning ブロックを組む。

    - ``""`` → ``None``。reasoning の欄を何も送らない
    - ``"none"`` → 従来どおり OpenRouter と DeepSeek の両方で明示的に無効化
    - それ以外 → OpenRouter 統一 envelope の ``reasoning.effort`` だけを送る

    config 経路と invoke の per-call override の両方が本関数を共有し、
    無効化 field と有効化 field を同時に送らない。
    """
    if effort == "":
        return None
    if effort != "none":
        return {"reasoning": {"effort": effort}}
    return {
        # OpenRouter 統一 envelope (primary control path)
        "reasoning": {
            "effort": "none",
            # exclude=True で response から reasoning token 本文を剥がす (= prompt
            # cache hit / cost 計測の安定化。なお tool-calling 経路では本文は
            # どのみち返らず、reasoning_token 数だけ usage に残る)
            "exclude": True,
        },
        # DeepSeek API native kill switch。OpenRouter が provider passthrough
        # するときに reasoning envelope を読み落とすケースの保険
        "thinking": {"type": "disabled"},
    }


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


_Result = TypeVar("_Result")


class LiteLLMClient(
    ILLMClient,
    IEpisodicChunkSubjectiveCompletionPort,
    IShortTermMemorySummaryCompletionPort,
    IShortTermMemoryLongSummaryCompletionPort,
    EpisodeWritingCompletion,
):
    """
    LiteLLM の completion API で messages + tools を送り、1 つの tool_call を返す実装。
    tool_choice="required" で 1 ツール必須とする。
    """

    def __init__(
        self,
        model: str = _DEFAULT_MODEL,
        api_key: str | None = None,
        api_key_env_var: str = _ENV_VAR_API_KEY,
        api_base: str | None = None,
        timeout_seconds: float | None = None,
        openrouter_provider: str | None = None,
        openrouter_quantization: str | None = None,
        reasoning_effort: str = _DEFAULT_REASONING_EFFORT,
        max_output_tokens: int | None = None,
        wall_cap_seconds: float | None = None,
        rate_limit_retry_attempts: int = _DEFAULT_RATE_LIMIT_RETRY_ATTEMPTS,
        rate_limit_retry_base_sleep: float = _DEFAULT_RATE_LIMIT_RETRY_BASE_SLEEP,
        aux_call_sink: AuxLlmCallSink | None = None,
    ) -> None:
        if not isinstance(model, str) or not model.strip():
            raise ValueError("model must be a non-empty string")
        if not isinstance(api_key_env_var, str) or not api_key_env_var.strip():
            raise ValueError("api_key_env_var must be a non-empty string")
        if api_key is not None and not isinstance(api_key, str):
            raise TypeError("api_key must be str or None")
        if api_base is not None and not isinstance(api_base, str):
            raise TypeError("api_base must be str or None")
        if api_key is None:
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
        self._api_base = resolved_base or None

        # PR #444: timeout を明示。設定引数 > default の優先で解決し、毎呼び
        # 出しの litellm.completion に渡す。これがないと litellm 既定 6000 秒
        # (= 100 分) で長期 hang を許容してしまう。
        self._timeout_seconds = (
            float(timeout_seconds)
            if timeout_seconds is not None
            else _DEFAULT_LLM_TIMEOUT_SECONDS
        )

        self._openrouter_routing: dict[str, Any] | None = _build_openrouter_routing(
            provider=openrouter_provider,
            quantization=openrouter_quantization,
        )

        self._reasoning_effort = _validate_reasoning_effort(
            reasoning_effort,
            source_label="reasoning_effort",
        )
        self._reasoning_block: dict[str, Any] | None = _build_reasoning_block(
            self._reasoning_effort
        )
        # thinking のトークン数も出力の上限に数えられる。OpenRouter の
        # reasoning.max_tokens は effort と同時に送れず、DeepSeek に効くかも
        # ドキュメントに無いので、どの provider でも効く top-level で抑える (#1595)。
        if max_output_tokens is not None and max_output_tokens < 1:
            raise ValueError("max_output_tokens must be 1 or greater")
        self._max_output_tokens = max_output_tokens

        # OpenRouter は api_base が openrouter ドメインかで判定する。
        # ``extra_body.usage.include=True`` を付けると response.usage.cost に
        # USD コストを乗せて返してくれる (per-call cost を計測したい)。
        # OpenAI 直結 / vLLM には影響しない (api_base が違うので付かない)。
        self._is_openrouter_base: bool = _detect_openrouter_base(self._api_base)

        if rate_limit_retry_attempts < 0:
            raise ValueError("rate_limit_retry_attempts must be 0 or greater")
        if rate_limit_retry_base_sleep < 0:
            raise ValueError("rate_limit_retry_base_sleep must be 0 or greater")
        self._rate_limit_retry_attempts = int(rate_limit_retry_attempts)
        self._rate_limit_retry_base_sleep = float(rate_limit_retry_base_sleep)

        # Wall-time hard cap: httpx の per-recv read timeout が効かないケースの
        # 保険として、`concurrent.futures.ThreadPoolExecutor.result(timeout=)`
        # で wall-time を独立に強制する。default は self._timeout_seconds + 5s
        # (httpx 経路が正常に動くケースの邪魔をしない)。
        self._wall_cap_seconds = (
            float(wall_cap_seconds)
            if wall_cap_seconds is not None
            else self._timeout_seconds + _DEFAULT_WALL_CAP_BUFFER_SECONDS
        )
        if self._wall_cap_seconds <= 0:
            raise ValueError("wall_cap_seconds must be greater than 0")

        self._aux_call_sink = aux_call_sink
        self._logger = logging.getLogger(self.__class__.__name__)

    def _call_with_wall_cap(self, call_fn: Callable[[], _Result]) -> _Result:
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
            from litellm import Timeout as LitellmTimeout
        except ImportError:  # pragma: no cover
            LitellmTimeout = Exception  # type: ignore

        # **executor を `with` で囲まない。** `with` の退出は
        # `shutdown(wait=True)` なので、cap で例外を投げても下位の call が
        # 終わるまでブロックし、「hard cap」が実質無効だった (実測: cap 0.5s /
        # call 3s で、例外は 0.5s・退出は 3.0s)。供物競争 run では cap 95s に
        # 対して 13 件が待ち切っており、run 時間の 16% を占めていた。
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        try:
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
        finally:
            # 待たずに解放する。走り続けるスレッドは下位 call が終われば
            # 自分で片付く (cancel_futures は待ち行列だけを落とすので、
            # 実行中の 1 本には効かない)。
            ex.shutdown(wait=False)

    def _call_with_selective_retry(self, call_fn: Callable[[], _Result]) -> _Result:
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
        last_exc: BaseException | None = None
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
    ) -> dict[str, Any] | None:
        """litellm.completion に渡す ``extra_body`` を組み立てる。

        - provider routing (OPENROUTER_PROVIDER 等の env が設定されているとき)
        - usage.include (api_base が OpenRouter のとき、cost を返してもらう)
        - reasoning + thinking (reasoning model 用、default OFF)

        ``reasoning_override`` に何か渡された場合 (sentinel 以外)、構築時の既定
        ``self._reasoning_block`` の代わりにその値を使う (``None`` を渡せば「この
        呼び出しは reasoning を一切 inject しない」を意味する)。

        どれも要らないときは None を返す (= extra_body を一切渡さない)。
        """
        block: dict[str, Any] = {}
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

    def completion_base_kwargs(
        self, *, reasoning_effort: str | None = None
    ) -> dict[str, Any]:
        """ツール無しの chat completion 用（Episode Encoder 等）。カスタム base 無しでは api_key が必須。

        OpenRouter provider routing env が設定されている場合、``extra_body`` を
        自動付与する (provider / quantization の固定)。さらに api_base が
        OpenRouter なら ``usage.include=True`` も同 ``extra_body`` に乗せて cost
        を返してもらう。

        ``reasoning_effort`` を渡すと、その補助呼び出しだけ構築時の既定を
        上書きする。``invoke`` と同じく ``None`` は既定を継承し、``"none"``
        は明示的な無効化 block を送る。
        """
        self._assert_can_call_litellm()
        effective_reasoning_effort = (
            self._reasoning_effort
            if reasoning_effort is None
            else _validate_reasoning_effort(reasoning_effort)
        )
        base: dict[str, Any] = {
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
        reasoning_override = (
            _NO_REASONING_OVERRIDE
            if reasoning_effort is None
            else _build_reasoning_block(effective_reasoning_effort)
        )
        extra_body = self._build_extra_body(reasoning_override=reasoning_override)
        if extra_body is not None:
            base["extra_body"] = extra_body
        return base

    @property
    def openrouter_routing(self) -> dict[str, Any] | None:
        """現在 inject される OpenRouter routing を返す (実験 trace 等の観測用)。"""
        if self._openrouter_routing is None:
            return None
        return copy.deepcopy(self._openrouter_routing)

    def invoke(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_choice: ToolChoice = "required",
        *,
        metrics_sink: LlmCallMetricsSink | None = None,
        reasoning_effort: str | None = None,
        prompt_capture_context: Any | None = None,
        call_phase: str = "one_step",
        session_id: str | None = None,
    ) -> dict[str, Any] | None:
        """
        1 回の LLM 呼び出しを行い、tool_call があれば {"name": str, "arguments": dict} を返す。
        tool_call が無い場合やパースに失敗した場合は None を返す。
        API エラー時は LlmApiCallException を投げる。

        ``metrics_sink`` が渡された場合、呼び出し成否によらず ``LlmCallMetrics`` を 1 件
        sink に流す (実験 #356: τ_sim 設定根拠 + scenario cost 評価用)。

        ``reasoning_effort`` を渡すと、その 1 呼び出しだけ構築時の既定 (env) を
        上書きして reasoning の effort を変える。``None``
        なら既定のまま (既存挙動)。未知値は ``ValueError``。tool-calling 経路では
        reasoning 本文は返らないが、reasoning_token 数は usage 経由で metrics に載る。

        ``call_phase`` は観測用。既存の 1段階呼び出しは ``one_step``、reason-first
        2段階ターンでは呼び出し側が ``assess_phase`` / ``action_phase`` を指定する。

        ``session_id`` は OpenRouter の sticky routing 用で、同じ会話中は固定する。
        OpenRouter 以外へは送らず、messages の内容にも混ぜない。
        """
        self._assert_can_call_litellm()
        if reasoning_effort is None:
            effective_reasoning_effort = self._reasoning_effort
            reasoning_override: Any = _NO_REASONING_OVERRIDE
        else:
            effective_reasoning_effort = _validate_reasoning_effort(reasoning_effort)
            reasoning_override = _build_reasoning_block(effective_reasoning_effort)
        recorded_reasoning_effort = (
            effective_reasoning_effort
            if effective_reasoning_effort not in {"", "none"}
            else reasoning_effort
        )
        start_monotonic = time.monotonic()
        try:
            completion_kw: dict[str, Any] = {
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
            if self._max_output_tokens is not None:
                completion_kw["max_tokens"] = self._max_output_tokens
            if self._is_openrouter_base and session_id is not None:
                normalized_session_id = session_id.strip()
                if not normalized_session_id:
                    raise ValueError("session_id must not be empty")
                if len(normalized_session_id) > 256:
                    raise ValueError("session_id must be 256 characters or fewer")
                completion_kw["session_id"] = normalized_session_id
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
            elif (
                effective_reasoning_effort not in {"", "none"}
                and tool_choice == "required"
                and "does not support this tool_choice" in str(e)
            ):
                error_code = "LLM_REASONING_REQUIRED_UNSUPPORTED"
            error_detail = str(e)
            if error_code == "LLM_REASONING_REQUIRED_UNSUPPORTED":
                error_detail = (
                    "thinking を有効にした provider が tool_choice='required' を"
                    f"拒否しました (reasoning_effort={effective_reasoning_effort}): {e}"
                )
            self._emit_metrics(
                metrics_sink,
                wall_latency_ms=wall_latency_ms,
                prompt_tokens=0,
                completion_tokens=0,
                success=False,
                error_code=error_code,
                # 例外本文 (provider 名・provider エラーコードを含む) を truncate して
                # trace に残す。error_code だけでは「なぜ失敗したか」が分からない。
                error_detail=error_detail[:_ERROR_DETAIL_MAX_CHARS],
                reasoning_effort=recorded_reasoning_effort,
                tool_choice=tool_choice,
                phase=call_phase,
                llm_call_id=_extract_llm_call_id(prompt_capture_context),
            )
            self._record_prompt_capture(
                prompt_capture_context,
                request_kwargs=completion_kw if "completion_kw" in locals() else {},
                response=None,
                error=e,
                output=None,
                metrics={
                    "wall_latency_ms": wall_latency_ms,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "cached_tokens": 0,
                    "reasoning_tokens": 0,
                    "cost_usd": 0.0,
                    "success": False,
                    "error_code": error_code,
                    "error_detail": error_detail[:_ERROR_DETAIL_MAX_CHARS],
                    "reasoning_effort": recorded_reasoning_effort,
                    "tool_choice": tool_choice,
                    "phase": call_phase,
                },
            )
            self._logger.exception("LiteLLM completion failed: %s", e)
            raise LlmApiCallException(
                f"LLM API call failed: {error_detail}",
                error_code=error_code,
                cause=e,
            ) from e
        wall_latency_ms = int((time.monotonic() - start_monotonic) * 1000)
        prompt_tokens, completion_tokens, cached_tokens = self._extract_token_usage(response)
        reasoning_tokens = self._extract_reasoning_tokens(response)
        cost_usd = self._extract_cost_usd(response)
        tool_call_combination = self._extract_tool_call_combination(response)
        discarded_tool_calls = (
            len(tool_call_combination) - 1 if tool_call_combination is not None else 0
        )
        if discarded_tool_calls:
            self._logger.warning(
                "LLM returned multiple tool calls; executing the first and discarding %d",
                discarded_tool_calls,
            )
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
            reasoning_effort=recorded_reasoning_effort,
            tool_choice=tool_choice,
            phase=call_phase,
            llm_call_id=_extract_llm_call_id(prompt_capture_context),
            discarded_tool_calls=discarded_tool_calls,
            tool_call_combination=tool_call_combination,
        )
        self._record_prompt_capture(
            prompt_capture_context,
            request_kwargs=completion_kw,
            response=response,
            error=None,
            output=tool_call,
            metrics={
                "wall_latency_ms": wall_latency_ms,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "cached_tokens": cached_tokens,
                "reasoning_tokens": reasoning_tokens,
                "cost_usd": cost_usd,
                "success": tool_call is not None,
                "error_code": None if tool_call is not None else "NO_TOOL_CALL",
                "reasoning_effort": recorded_reasoning_effort,
                "tool_choice": tool_choice,
                "phase": call_phase,
                "discarded_tool_calls": discarded_tool_calls,
                **(
                    {"tool_call_combination": list(tool_call_combination)}
                    if tool_call_combination is not None
                    else {}
                ),
            },
        )
        return tool_call

    @staticmethod
    def _extract_tool_call_combination(response: Any) -> tuple[str, ...] | None:
        """複数 tool_call の名前だけを返却順で返し、通常の1件なら None にする。"""

        try:
            choices = getattr(response, "choices", None) or []
            if not choices:
                return None
            message = getattr(choices[0], "message", None)
            tool_calls = getattr(message, "tool_calls", None) or []
            if len(tool_calls) <= 1:
                return None
            return tuple(
                str(getattr(getattr(call, "function", None), "name", ""))
                for call in tool_calls
            )
        except (TypeError, AttributeError):
            return None

    @staticmethod
    def _extract_reasoning_tokens(response: Any) -> int:
        """litellm レスポンスの ``usage.completion_tokens_details.reasoning_tokens`` を
        best-effort で取り出す。reasoning model が思考に使ったトークン数。

        tool-calling 経路では reasoning 本文は返らないが、このトークン数は usage に
        残るので「実際に何回・どれだけ熟考したか」の観測点になる。
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
        sink: LlmCallMetricsSink | None,
        *,
        wall_latency_ms: int,
        prompt_tokens: int,
        completion_tokens: int,
        success: bool,
        error_code: str | None,
        cached_tokens: int = 0,
        reasoning_tokens: int = 0,
        cost_usd: float = 0.0,
        error_detail: str = "",
        reasoning_effort: str | None = None,
        tool_choice: ToolChoice = "",
        phase: str = "one_step",
        llm_call_id: str | None = None,
        discarded_tool_calls: int = 0,
        tool_call_combination: tuple[str, ...] | None = None,
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
                error_detail=error_detail,
                reasoning_effort=reasoning_effort,
                tool_choice=tool_choice,
                phase=phase,
                llm_call_id=llm_call_id,
                discarded_tool_calls=discarded_tool_calls,
                tool_call_combination=tool_call_combination,
            )
            sink.record(metrics)
        except Exception:
            # メトリクス記録の失敗が LLM 呼び出し本体の挙動を倒さないよう吸収。
            self._logger.exception("metrics_sink.record failed")

    def _record_prompt_capture(
        self,
        prompt_capture_context: Any | None,
        *,
        request_kwargs: Mapping[str, Any],
        response: Any,
        error: BaseException | None,
        output: Mapping[str, Any] | None,
        metrics: Mapping[str, Any],
    ) -> None:
        if prompt_capture_context is None:
            return
        prompt_capture_context.sink.record_call(
            context=prompt_capture_context.context,
            request_kwargs=request_kwargs,
            response=response,
            error=error,
            output=output,
            metrics=metrics,
        )

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

    def complete_episode_subjective_json(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """
        tools 無しで JSON object を強制する chat completion を行いパース済み dict を返す。
        失敗や不正 JSON ではここでは補完せず LlmApiCallException を送出し、呼び出し元が草案テンプレへフォールバックする。
        """
        return self._complete_aux_json(messages, AuxLlmComponent.EPISODE_SUBJECTIVE)

    def _complete_aux_json(
        self,
        messages: list[dict[str, Any]],
        component: AuxLlmComponent,
    ) -> dict[str, Any]:
        start_monotonic = time.monotonic()
        response: Any = None
        try:
            response = self._send_json_request(messages)
            parsed = self._parse_json_object(response)
        except LlmApiCallException as e:
            self._record_aux_call(
                component,
                response=response,
                start_monotonic=start_monotonic,
                error_code=e.error_code,
            )
            raise
        self._record_aux_call(
            component,
            response=response,
            start_monotonic=start_monotonic,
            error_code=None,
        )
        return parsed

    def _record_aux_call(
        self,
        component: AuxLlmComponent,
        *,
        response: Any,
        start_monotonic: float,
        error_code: str | None,
    ) -> None:
        if self._aux_call_sink is None:
            return
        try:
            tokens: tuple[int | None, int | None, int | None] = (None, None, None)
            if getattr(response, "usage", None) is not None:
                tokens = self._extract_token_usage(response)
            prompt_tokens, completion_tokens, cached_tokens = tokens
            self._aux_call_sink.record(
                AuxLlmCall(
                    component=component,
                    model=self._model,
                    wall_latency_ms=int((time.monotonic() - start_monotonic) * 1000),
                    success=error_code is None,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cached_tokens=cached_tokens,
                    cost_usd=self._extract_reported_cost_usd(response),
                    error_code=error_code,
                )
            )
        except Exception:
            self._logger.exception("aux_call_sink.record failed")

    @staticmethod
    def _extract_reported_cost_usd(response: Any) -> float | None:
        usage = getattr(response, "usage", None)
        cost = getattr(usage, "cost", None)
        if cost is None and isinstance(usage, dict):
            cost = usage.get("cost")
        if cost is None:
            return None
        try:
            return float(cost)
        except (TypeError, ValueError):
            return None

    def _send_json_request(self, messages: list[dict[str, Any]]) -> Any:
        # JSON 抽出は行動選択ではない。agent turn の thinking 設定を継承すると
        # 費用だけでなく json_object との provider 互換性も悪化するため、
        # knob を増やさず全補助 JSON 呼び出しで明示的に止める。
        kwargs = self.completion_base_kwargs(reasoning_effort="none")
        try:
            # SDK 透過 retry は max_retries=0 で無効化済み。RateLimit / 一時 5xx の
            # みアプリ層で短い backoff retry する。
            return self._call_with_selective_retry(
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

    @staticmethod
    def _parse_json_object(response: Any) -> dict[str, Any]:
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

    def complete_short_term_summary_json(
        self,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """tools 無しで L4 mid summary JSON object を返す (Phase 2)。

        既存の json_object 強制完了をそのまま使う (LLM 側から見れば同じ呼出)。
        prompt 構築や parse は ``ShortTermMemorySummaryService`` 側の責務。
        """
        return self._complete_aux_json(messages, AuxLlmComponent.SHORT_TERM_SUMMARY)

    def complete_short_term_long_summary_json(
        self,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """tools 無しで L5 long summary JSON object を返す (Phase 3)。

        既存の json_object 強制完了をそのまま使う (LLM 側から見れば同じ呼出)。
        prompt 構築や parse は ``ShortTermMemoryLongSummaryService`` 側の責務。
        """
        return self._complete_aux_json(messages, AuxLlmComponent.SHORT_TERM_LONG_SUMMARY)

    def complete_episode_writing_json(
        self,
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """目次つきのエピソードの書き起こし (#1626)。要約と同じく熟考を止めて送る。"""
        return self._complete_aux_json(messages, AuxLlmComponent.EPISODE_WRITING)

    def _parse_tool_call(
        self,
        response: Any,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
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
        arguments: dict[str, Any] = {}
        if args_str and isinstance(args_str, str):
            try:
                arguments = json.loads(args_str) if args_str.strip() else {}
            except (json.JSONDecodeError, TypeError):
                arguments = {}
        if not isinstance(arguments, dict):
            arguments = {}
        result = {"name": name, "arguments": arguments}
        call_id = getattr(first, "id", None)
        if isinstance(call_id, str) and call_id:
            result["tool_call_id"] = call_id
        return result


def _extract_llm_call_id(prompt_capture_context: Any | None) -> str | None:
    """prompt dataset context から trace 結合用の llm_call_id を取り出す。"""

    if prompt_capture_context is None:
        return None
    context = getattr(prompt_capture_context, "context", None)
    value = getattr(context, "llm_call_id", None)
    return str(value) if value else None
