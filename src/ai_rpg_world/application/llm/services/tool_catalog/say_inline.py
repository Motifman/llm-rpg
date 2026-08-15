"""行動ツール向けの ``say_inline`` 共通 JSON Schema 断片。

実験 #29 OFF 分析のユーザ feedback:
「喋りながら渡す、喋りながら移動する→これは移動系ツールの引数に軽く制限を
 つけた一言を喋れるようにするとかで解決できそう、その場の人にしか届かない
 とか」

設計:
- 200 char 上限の短い一言 (= 報告、段取りの相談、呼びかけ、確認)
- ``SpeechChannel.SAY`` を採用 (同 spot + 隣接 1 hop に届く)
- 未指定 / 空文字なら何もしない (silent)
- 過剰な多弁化を防ぐため上限 200 char を強制

**channel 選定の根拠 (レビュー反映 #422 MEDIUM-4)**:

ユーザ要件は厳密には「その場の人にしか届かない」だが、現状 ``SpeechChannel``
列挙には WHISPER (同 spot 内 1 人だけ) / SAY (同 spot + 隣接) /
SHOUT (2 hop まで) しか無く、本機能向けの「同 spot 全員のみ」channel は
無い。専用 channel を新設するコストは:

- speech / observation / recipient_strategy 全経路にケーブル追加が必要
- 「同 spot 全員」セマンティクスは SAY の特殊化なので情報量増加少ない
- inline speech は「ささやかな付帯発話」用途なので、隣接 spot に漏れても
  物語的に問題ない (「隣の部屋にも聞こえた」が自然な場面も多い)

ため SAY 流用とする。「同 spot 内に厳密に閉じたい」要望が実走で強く出たら、
INLINE 専用 channel を切る後続 PR を立てる。
"""

from __future__ import annotations


SAY_INLINE_MAX_LENGTH = 200
#: **この文は 21 ツールに複製される**。言い回しは削るが、**発話の種類は削らない**。
#:
#: 「報告・相談・呼びかけ・確認」の 4 つは、それぞれ別の発話行為である (相談は
#: 答えを求める、確認は合っているかを問う)。**数文字を惜しんで種類を減らすと、
#: その種類の発話が起きなくなる。**
#: 要点 + 参照。詳しくは system prompt の【独白と一言の書き方】にある。
SAY_INLINE_DEFAULT_DESCRIPTION = (
    "この行動をしながら発する一言 (任意、200 字以内)。"
    "書き方は【独白と一言の書き方】。"
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
