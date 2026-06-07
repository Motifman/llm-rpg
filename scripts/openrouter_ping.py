"""OpenRouter (OpenAI 互換) 経由で LiteLLMClient の疎通を確認する最小スクリプト。

目的:
- OpenRouter API key + base URL の設定が正しいかをまず確認する
- 本番経路と同じ ``LiteLLMClient`` で 1 call 叩き、wall latency / token usage を出す
- 失敗時は error_code だけ表示し、key を出力しない (誤って repo に貼る事故を防ぐ)

前提:
- ``.env`` (gitignore 済) に以下を書いておく:

    OPENAI_API_KEY=sk-or-v1-...           # OpenRouter のキー
    OPENAI_API_BASE=https://openrouter.ai/api/v1

  ``LiteLLMClient`` は ``OPENAI_API_KEY`` / ``OPENAI_API_BASE`` を見る実装なので、
  OpenRouter のキーをそのままここに入れて使う。

使い方:

    # 既定モデル (google/gemma-3-27b-it) で 1 call
    python scripts/openrouter_ping.py

    # モデル指定
    python scripts/openrouter_ping.py --model openrouter/google/gemma-3-27b-it

    # JSON mode 疎通もしたい場合
    python scripts/openrouter_ping.py --json

注意:
- 本スクリプトは API key の値を **絶対に stdout / log に出さない**。
- 1 call のみ。loop しない (誤って課金が膨らむのを防ぐ)。
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from typing import Any, Dict

import litellm

from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient


# OpenRouter で gemma 系を使う場合の既定値。実際の id は OpenRouter dashboard の
# Models ページで確認すること。litellm は "openrouter/<provider>/<model>" 形式
# でも "openai/<model>" 形式 (api_base 指定時) でも受け付ける。
_DEFAULT_PING_MODEL = "openrouter/google/gemma-4-31b-it"


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="OpenRouter 疎通確認 (LiteLLMClient 経由 / 1 call)",
    )
    parser.add_argument(
        "--model",
        default=_DEFAULT_PING_MODEL,
        help=(
            "litellm に渡す model id。OpenRouter なら 'openrouter/<provider>/<model>' "
            "形式が安全。既定: %(default)s"
        ),
    )
    parser.add_argument(
        "--prompt",
        default="日本語で 'pong' とだけ答えてください。",
        help="送る user prompt (極小に保つこと)。",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=16,
        help="completion の max_tokens 上限 (課金事故防止)。",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="JSON mode (response_format=json_object) で叩く。",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help=(
            "OpenRouter の provider を 1 つに固定する (例: 'DeepInfra')。"
            "指定時は ``extra_body.provider.order=[<name>], allow_fallbacks=False`` "
            "を付ける。未指定なら OpenRouter のルーティングに任せる。"
        ),
    )
    parser.add_argument(
        "--quantization",
        default=None,
        help=(
            "provider の variant を quantization (fp8 / fp4 / bf16 等) で絞る。"
            "同 provider が複数 quant を出している場合 (例: DeepInfra の turbo=fp4 / fp8) "
            "に意図したものに固定するため。"
        ),
    )
    parser.add_argument(
        "--require-params",
        action="store_true",
        help=(
            "provider.require_parameters=true を付け、リクエストに含めた param を全て"
            "サポートする provider のみに限定する (tools / response_format を要求する"
            "ときの安全弁)。"
        ),
    )
    parser.add_argument(
        "--list-models",
        action="store_true",
        help=(
            "1 call も叩かず、利用可能 model 一覧を OpenRouter から取得して表示する。"
            "id の正しい綴りを確認するときに使う。"
        ),
    )
    parser.add_argument(
        "--list-providers",
        action="store_true",
        help=(
            "--model に渡した id を serve している provider 一覧を OpenRouter から"
            "取得して表示する (provider 名 / context / quantization / pricing)。"
            "DeepInfra Turbo の正確な綴りを取りたいとき用。"
        ),
    )
    return parser


def _redact_url(url: str) -> str:
    """api_base を安全に出力するための簡易マスク (query/fragment を捨てる)。"""
    head = url.split("?", 1)[0].split("#", 1)[0]
    return head


def _check_environment() -> None:
    """.env 自動読込は LiteLLMClient に任せるが、最低限のヒントを出す。"""
    if not os.environ.get("OPENAI_API_KEY"):
        # ここではまだ .env が load されていないので「無いかも」しか言えない。
        # LiteLLMClient のコンストラクタが load_dotenv するので、後段で再判定する。
        sys.stderr.write(
            "[hint] OPENAI_API_KEY が shell env に無いので .env を読みに行きます。\n"
        )


def _provider_extra_body(
    provider: str | None,
    quantization: str | None = None,
    require_params: bool = False,
) -> Dict[str, Any]:
    """``--provider`` / ``--quantization`` / ``--require-params`` を OpenRouter 仕様の
    ``extra_body.provider`` に組み立てる。"""
    if not provider and not quantization and not require_params:
        return {}
    provider_block: Dict[str, Any] = {}
    if provider:
        provider_block["order"] = [provider]
        provider_block["allow_fallbacks"] = False
    if quantization:
        provider_block["quantizations"] = [quantization]
    if require_params:
        provider_block["require_parameters"] = True
    return {"extra_body": {"provider": provider_block}}


def _ping_chat(
    client: LiteLLMClient,
    prompt: str,
    max_tokens: int,
    provider: str | None,
    quantization: str | None = None,
    require_params: bool = False,
) -> Dict[str, Any]:
    """tools 無し / JSON 強制無しの素の chat completion を 1 回だけ叩く。"""
    kwargs = client.completion_base_kwargs()
    kwargs["max_tokens"] = max_tokens
    kwargs.update(_provider_extra_body(provider, quantization, require_params))
    messages = [{"role": "user", "content": prompt}]
    started = time.monotonic()
    response = litellm.completion(messages=messages, **kwargs)
    latency_ms = int((time.monotonic() - started) * 1000)
    return _summarize(response, latency_ms)


def _ping_json(
    client: LiteLLMClient,
    prompt: str,
    max_tokens: int,
    provider: str | None,
    quantization: str | None = None,
    require_params: bool = False,
) -> Dict[str, Any]:
    """JSON mode (response_format=json_object) で 1 回叩く。"""
    kwargs = client.completion_base_kwargs()
    kwargs["max_tokens"] = max_tokens
    kwargs.update(_provider_extra_body(provider, quantization, require_params))
    messages = [
        {
            "role": "system",
            "content": '{"reply": "..."} の形の JSON を返してください。それ以外は出力禁止。',
        },
        {"role": "user", "content": prompt},
    ]
    started = time.monotonic()
    response = litellm.completion(
        messages=messages,
        response_format={"type": "json_object"},
        **kwargs,
    )
    latency_ms = int((time.monotonic() - started) * 1000)
    return _summarize(response, latency_ms)


def _list_providers(model_id: str) -> int:
    """OpenRouter /models/<id>/endpoints を叩いて provider 一覧を出す。"""
    import urllib.parse
    import urllib.request

    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        sys.stderr.write("[error] OPENAI_API_KEY (= OpenRouter key) が未設定\n")
        return 2
    # litellm 用に "openrouter/" prefix を付けて渡されるパターンを剥がす
    bare_id = model_id
    if bare_id.startswith("openrouter/"):
        bare_id = bare_id[len("openrouter/"):]
    safe = urllib.parse.quote(bare_id, safe="/")
    url = f"https://openrouter.ai/api/v1/models/{safe}/endpoints"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        sys.stderr.write(f"[error] /endpoints fetch failed: {type(e).__name__}: {e}\n")
        return 3
    data = payload.get("data") or {}
    endpoints = data.get("endpoints") or []
    sys.stdout.write(f"model: {data.get('id') or bare_id}\n")
    sys.stdout.write(f"providers serving this model: {len(endpoints)}\n")
    sys.stdout.write("---\n")
    for ep in endpoints:
        sys.stdout.write(json.dumps(ep, ensure_ascii=False) + "\n")
    return 0


def _list_models(filter_substr: str | None = None) -> int:
    """OpenRouter /models を叩いて id 一覧を出す (1 call ぶんの GET)。"""
    import urllib.request

    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        sys.stderr.write("[error] OPENAI_API_KEY (= OpenRouter key) が未設定\n")
        return 2
    req = urllib.request.Request(
        "https://openrouter.ai/api/v1/models",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        sys.stderr.write(f"[error] /models fetch failed: {type(e).__name__}: {e}\n")
        return 3
    rows = payload.get("data", []) or []
    if filter_substr:
        needle = filter_substr.lower()
        rows = [r for r in rows if needle in (r.get("id", "").lower())]
    for r in rows:
        sys.stdout.write(f"{r.get('id')}\t{r.get('name', '')}\n")
    sys.stdout.write(f"--- {len(rows)} model(s)\n")
    return 0


def _summarize(response: Any, latency_ms: int) -> Dict[str, Any]:
    """litellm 応答から人が見て嬉しい最小情報だけ抜く。"""
    if not response or not getattr(response, "choices", None):
        return {"ok": False, "reason": "empty_response", "latency_ms": latency_ms}
    choice0 = response.choices[0]
    msg = getattr(choice0, "message", None)
    content = getattr(msg, "content", None) if msg else None
    usage = getattr(response, "usage", None)
    prompt_tokens = getattr(usage, "prompt_tokens", None) if usage else None
    completion_tokens = getattr(usage, "completion_tokens", None) if usage else None
    return {
        "ok": True,
        "latency_ms": latency_ms,
        "model": getattr(response, "model", None),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "content_snippet": (content or "")[:120],
    }


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING)
    args = _build_arg_parser().parse_args(argv)

    _check_environment()

    if args.list_models:
        # --model を filter として使う (短く済むので)
        filter_str = args.model if args.model != _DEFAULT_PING_MODEL else None
        return _list_models(filter_str)

    if args.list_providers:
        return _list_providers(args.model)

    try:
        client = LiteLLMClient(model=args.model)
    except Exception as e:
        sys.stderr.write(f"[error] failed to build LiteLLMClient: {type(e).__name__}: {e}\n")
        return 2

    base = os.environ.get("OPENAI_API_BASE", "").strip()
    sys.stdout.write(f"model     = {args.model}\n")
    sys.stdout.write(f"api_base  = {_redact_url(base) if base else '(default openai)'}\n")
    sys.stdout.write(f"api_key   = {'set' if os.environ.get('OPENAI_API_KEY') else 'MISSING'}\n")
    sys.stdout.write("---\n")

    if args.provider:
        sys.stdout.write(f"provider  = pinned to '{args.provider}' (no fallback)\n")
    try:
        if args.json:
            summary = _ping_json(
                client,
                args.prompt,
                args.max_tokens,
                args.provider,
                args.quantization,
                args.require_params,
            )
        else:
            summary = _ping_chat(
                client,
                args.prompt,
                args.max_tokens,
                args.provider,
                args.quantization,
                args.require_params,
            )
    except LlmApiCallException as e:
        sys.stderr.write(
            f"[error] LlmApiCallException error_code={e.error_code} message={e}\n"
        )
        return 3
    except Exception as e:
        sys.stderr.write(f"[error] {type(e).__name__}: {e}\n")
        return 4

    sys.stdout.write(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
