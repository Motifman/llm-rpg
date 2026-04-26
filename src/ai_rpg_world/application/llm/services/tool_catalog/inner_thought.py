"""全ツール共通の inner_thought JSON Schema 断片。"""

from __future__ import annotations

# 呼び出し元で上書きして A/B 比較用に使う
# 行動ルール（escape system）の説明と揃える。キー名は本番 `inner_thought` 固定。
INNER_THOUGHT_DEFAULT_DESCRIPTION = (
    "システムメッセージ先頭の【ペルソナ】（話し方・口調の手がかり）に揃えた、"
    "この行動を選ぶ直前の短い一文。観測者向けに表示される。未発見の事実を知った体で書かないこと。"
)

INNER_THOUGHT_TYPE_STRING = "string"
INNER_THOUGHT_MAX_LENGTH = 500


def inner_thought_property(
    description: str | None = None,
    *,
    max_length: int = INNER_THOUGHT_MAX_LENGTH,
) -> dict:
    return {
        "type": INNER_THOUGHT_TYPE_STRING,
        "description": description or INNER_THOUGHT_DEFAULT_DESCRIPTION,
        "maxLength": max_length,
        "minLength": 1,
    }


__all__ = [
    "INNER_THOUGHT_DEFAULT_DESCRIPTION",
    "INNER_THOUGHT_MAX_LENGTH",
    "inner_thought_property",
]
