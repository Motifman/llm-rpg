"""移動 / アイテム系ツール向けの ``say_inline`` 共通 JSON Schema 断片。

実験 #29 OFF 分析のユーザ feedback:
「喋りながら渡す、喋りながら移動する→これは移動系ツールの引数に軽く制限を
 つけた一言を喋れるようにするとかで解決できそう、その場の人にしか届かない
 とか」

設計:
- 80 char 上限の短い一言 (= ≒ 立ち去り際の一言、感謝、軽い指示)
- 同 spot の他プレイヤーにだけ届く SAY 相当 (1 hop の隣接には伝播しない想定。
  ただし実装上は SpeakChannel.SAY を使うので隣接 spot の audience にも届く。
  必要なら後続 PR で「INLINE 専用 channel」を切る)
- 未指定 / 空文字なら何もしない (silent)
- 過剰な多弁化を防ぐため上限 80 char を強制
"""

from __future__ import annotations


SAY_INLINE_MAX_LENGTH = 80
SAY_INLINE_DEFAULT_DESCRIPTION = (
    "立ち去り際 / 受け渡し際に同 spot へ向けて発する短い一言 (任意、80 字以内)。"
    "「ありがとう」「先に行く」のような付随発話用。空文字 / 未指定なら発話しない。"
    "長い speech が必要な場合は speech_speak を別途使う。"
)


def say_inline_property(
    description: str | None = None,
    *,
    max_length: int = SAY_INLINE_MAX_LENGTH,
) -> dict:
    return {
        "type": "string",
        "description": description or SAY_INLINE_DEFAULT_DESCRIPTION,
        "maxLength": max_length,
    }


__all__ = [
    "SAY_INLINE_MAX_LENGTH",
    "SAY_INLINE_DEFAULT_DESCRIPTION",
    "say_inline_property",
]
