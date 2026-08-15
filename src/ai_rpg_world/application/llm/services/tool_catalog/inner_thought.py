"""全ツール共通の inner_thought JSON Schema 断片。"""

from __future__ import annotations

# 呼び出し元で上書きして A/B 比較用に使う
# 行動ルール（escape system）の説明と揃える。キー名は本番 `inner_thought` 固定。
#: **この文は全ツールに複製される** (27 ツール分)。1 文字が 27 文字になるので、
#: 「説明の説明」にあたる言い回しは削る。
#:
#: ただし**質感の制約は一字も削らない**。「演技や情景描写ではない」「未発見の事実を
#: 知った体で書かない」の 2 つは、消すと独白が語りになったり、知らないはずのことを
#: 知っている風に書き始める。**この実験が見たいものそのものが壊れる。**
#: **要点だけを残し、詳しくは system prompt を指す。**
#:
#: この文は全ツールの schema に複製されるので、1 文字が 27 文字になる。同じ段落を
#: 27 回置く代わりに、**system prompt に 1 度だけ**書いて、ここからは指す。
#:
#: **純粋な指し示しにはしない。** 参照が効かなかったときに何も残らないと困るので、
#: 「何を書く引数か」の一文は必ず残す。
INNER_THOUGHT_DEFAULT_DESCRIPTION = (
    "この行動を選ぶ直前の、あなた自身の頭の中の独白を一文で。"
    "書き方は【独白と一言の書き方】。"
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
