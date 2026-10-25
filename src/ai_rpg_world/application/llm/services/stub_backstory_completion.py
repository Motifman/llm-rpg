"""実 LLM を呼ばない run で、いきさつを作る配線と trace を確かめるためのスタブ。"""

from __future__ import annotations

from typing import Any

_EVENT_LINE_PREFIX = "- "


def stub_backstory_completion(messages: list[dict[str, Any]]) -> dict[str, Any]:
    """まとめる範囲の最初の出来事を流れにした、いきさつの応答を返す。"""
    first_event = next(
        (line for line in messages[-1]["content"].splitlines() if line.startswith(_EVENT_LINE_PREFIX)),
        "",
    ).removeprefix(_EVENT_LINE_PREFIX)
    return {"compressed_activity": f"(スタブ) {first_event}", "emotional_summary": ""}


__all__ = ["stub_backstory_completion"]
