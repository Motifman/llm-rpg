from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional

from .base import CompletionRequest, CompletionResponse, LLMClient


class OpenAIClient(LLMClient):
    """OpenAI API クライアント。

    依存は遅延インポート（実行環境に openai が無い場合でも読み込み時エラーを防止）。
    APIキーは環境変数 `OPENAI_API_KEY` を使用。
    モデルは `OPENAI_MODEL`（未設定時は `gpt-4o-mini` を既定）。
    """

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    def complete(self, request: CompletionRequest) -> CompletionResponse:
        try:
            import openai  # type: ignore
        except Exception as e:  # pragma: no cover - import guard
            raise RuntimeError("openai ライブラリが見つかりません。requirementsに追加してください。") from e

        client = openai.OpenAI(api_key=self._api_key) if hasattr(openai, "OpenAI") else openai

        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})

        # 構造化出力（JSON）サポート: 有効な場合はJSONモードを設定
        response_json: Optional[Dict[str, Any]] = None

        if hasattr(client, "chat") and hasattr(client.chat, "completions"):
            # 旧SDK互換/仮API
            kwargs: Dict[str, Any] = {
                "model": self._model,
                "messages": messages,
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
            }
            if request.json_schema is not None:
                # 一部SDKでは response_format={"type":"json_object"} でJSON化
                kwargs["response_format"] = {"type": "json_object"}

            completions_obj = client.chat.completions
            # SDKの形状差異に対応: .create が直下にある場合/更にネストされている場合
            create_fn = getattr(completions_obj, "create", None)
            if callable(create_fn):
                resp = create_fn(**kwargs)
            elif hasattr(completions_obj, "completions") and callable(getattr(completions_obj.completions, "create", None)):
                resp = completions_obj.completions.create(**kwargs)
            else:
                raise RuntimeError("OpenAIクライアントの completions.create が見つかりませんでした。")
            choice = resp.choices[0]
            text = choice.message.content or ""
            if request.json_schema is not None:
                try:
                    response_json = json.loads(text)
                except Exception:
                    response_json = None

            usage = getattr(resp, "usage", None)
            return CompletionResponse(
                text=text,
                usage_prompt_tokens=getattr(usage, "prompt_tokens", None),
                usage_completion_tokens=getattr(usage, "completion_tokens", None),
                parsed_json=response_json,
            )

        # フォールバック（SDK差異への対応）
        raise RuntimeError("対応していないOpenAIクライアントインターフェースです。")


