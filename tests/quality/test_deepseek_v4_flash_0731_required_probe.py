"""DeepSeek V4 Flash 0731 の公式 endpoint が required に対応したかを調べる。"""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from ai_rpg_world.application.llm.exceptions import LlmApiCallException
from ai_rpg_world.infrastructure.llm.litellm_client import LiteLLMClient


_PROBE_TOOL = {
    "type": "function",
    "function": {
        "name": "report_probe_result",
        "description": "接続確認の結果を返す。",
        "parameters": {
            "type": "object",
            "properties": {
                "ok": {"type": "boolean"},
            },
            "required": ["ok"],
            "additionalProperties": False,
        },
    },
}


@pytest.mark.quality
def test_deepseek_official_still_rejects_required_tool_choice() -> None:
    """公式が required を拒む間は成功し、対応して呼べるようになったら失敗する。"""
    load_dotenv()
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        pytest.skip("OPENAI_API_KEY が無いため OpenRouter 品質プローブを省略する")

    client = LiteLLMClient(
        model="openrouter/deepseek/deepseek-v4-flash-0731",
        api_key=api_key,
        api_base="https://openrouter.ai/api/v1",
        timeout_seconds=30,
        openrouter_provider="DeepSeek",
        reasoning_effort="none",
        rate_limit_retry_attempts=0,
    )

    try:
        result = client.invoke(
            messages=[
                {
                    "role": "user",
                    "content": "report_probe_result を呼び出してください。",
                }
            ],
            tools=[_PROBE_TOOL],
            tool_choice="required",
        )
    except LlmApiCallException as exc:
        error_text = str(exc)
        assert "404" in error_text and "No endpoints found" in error_text, error_text
        return

    pytest.fail(
        "DeepSeek 公式 endpoint が tool_choice=required に対応しました。"
        f"Cloudflare 固定を再検討してください: result={result!r}"
    )
