"""【思い出せる出来事】の呼び名を指定して、エピソードの本文を思い出すツール (#1623)。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from ai_rpg_world.being.domain.episode_recall import RecallResult
from ai_rpg_world.being.domain.working_memory import EPISODE_INDEX_HEADING

HANDLES = "handles"
UNKNOWN_EPISODE_TEXT = "そのような記憶は思い出せない。"
MALFORMED_HANDLES_TEXT = (
    f"handles には、【{EPISODE_INDEX_HEADING}】に並ぶ ep_ で始まる呼び名を、"
    '1 件でも配列で渡してください (例: ["ep_3f2a7b"])。'
)


def episode_recall_description(max_handles: int) -> str:
    return (
        f"【{EPISODE_INDEX_HEADING}】に並ぶ自分の昔の出来事を、呼び名を指定して詳しく思い出す。"
        "目次の「思い出すとき」に今の場面が当てはまるとき、昔のことを人に話す前、"
        "似た場面で前にどうしたかを確かめたいときに使う。"
        f"1 回に {max_handles} 件まで、まとめて思い出せる。"
        "目次に無い呼び名は思い出せない。思い出すだけで、世界の出来事は起こさない。"
    )


def episode_recall_parameters(max_handles: int) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            HANDLES: {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": max_handles,
                "description": (
                    f"【{EPISODE_INDEX_HEADING}】の行の先頭にある ep_ で始まる呼び名。"
                    '1 件でも配列で渡す (例: ["ep_3f2a7b"])。'
                ),
            },
        },
        "required": [HANDLES],
    }


def read_handles(arguments: Mapping[str, object]) -> list[str] | None:
    """崩れていれば None。"""
    raw = arguments.get(HANDLES)
    if not isinstance(raw, list) or not raw:
        return None
    if not all(isinstance(h, str) and h.strip() for h in raw):
        return None
    return [h.strip() for h in raw]


def recall_call_text(tool_name: str, arguments: Mapping[str, object]) -> str:
    """古い run と同じく、呼び名の配列だけを JSON のまま引用する。"""
    if HANDLES not in arguments:
        return f"{tool_name}()"
    return f"{tool_name}({HANDLES}={json.dumps(arguments[HANDLES], ensure_ascii=False, separators=(',', ':'))})"


def too_many_handles_text(max_handles: int) -> str:
    return f"一度に思い出せるのは {max_handles} 件までです。呼び名を減らしてください。"


def recalled_text(results: tuple[RecallResult, ...]) -> str:
    return "\n".join(_result_text(r) for r in results)


def _result_text(result: RecallResult) -> str:
    if result.episode is None:
        return f"[{result.handle}] {UNKNOWN_EPISODE_TEXT}"
    return f"[{result.handle}] {result.episode.index.summary}\n  {result.episode.body}"
