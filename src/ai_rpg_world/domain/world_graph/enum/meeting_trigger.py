"""会議が始まった / 終わった理由の語彙。

## なぜ enum にするか (系統4)

観測の prose は理由ごとの表で引いていたが、理由が**生の文字列**だったため
**網羅を縛る相手がいなかった**。

    template = self._MEETING_TRIGGER_PROSE.get(
        event.trigger, "招集がかかった。全員が集まる。"
    )

新しい理由を足すと、誰が何をしたか分からない汎用文へ**静かに倒れる**。表に載せ
忘れたことは誰にも見えない。判断 #65 (enum で分岐するなら表にする) の対象だが、
enum が無いので網羅テストが書けなかった。

## 値は文字列のまま使う

``GamePhaseState.trigger`` は ``str`` で、``game_phase_codec`` が **snapshot へ直列化
している**。trace payload にも同じ値が乗る。型を変えると snapshot 互換 (設計判断
#15-#18) と過去 run の trace 分析に触るので、**フィールドは ``str`` のまま**にして、
生産側が ``.value`` を渡す。

こうすると語彙は 1 か所で宣言され、prose 表の網羅をテストで縛れる。wire 形式は
1 バイトも変わらない。

## なぜ 2 つの enum に分けるか

始まりの理由と終わりの理由は**集合が交わらない**。1 つにまとめると、prose 表が
「始まりの表に終わりの理由が無い」ことを網羅漏れと誤検出する。

## `trigger` という名前について

このリポジトリには無関係な `trigger` が 4 系統ある (map trigger / scenario event の
発火方式 / player outcome rule の契機 / この会議の理由)。**名前で grep すると全部
混ざる**ので、この語彙は型で区別する。
"""

from __future__ import annotations

from enum import Enum

__all__ = ["MeetingStartTrigger", "MeetingEndReason"]


class MeetingStartTrigger(Enum):
    """会議が始まった理由。"""

    #: 誰かが緊急ボタンを押した。
    EMERGENCY_BUTTON = "emergency_button"
    #: 誰かが倒れている者を見つけたと知らせた。
    BODY_REPORT = "body_report"


class MeetingEndReason(Enum):
    """会議が終わった理由。"""

    #: 投票が成立して結論が出た。
    VOTE_CONCLUDED = "vote_concluded"
    #: 誰も口を開かなくなり、議論が尽きた。
    SILENCE = "silence"
    #: 会議の時間上限に達した。
    TICK_LIMIT = "tick_limit"
