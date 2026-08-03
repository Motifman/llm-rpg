"""待ち時間を、世界の中にある単位で書く。

``あと 13 tick`` と出していた。**tick は世界の中に無い語** (#892)。
エージェントは毎ターン「現在時刻: 深夜 0:05」を見ているので、そこに揃える。
実 run 011 でインポスターがこの文を読んでいる。

対人行為と物体操作の両方が同じ文を出す。**書き写すと、片方だけ tick に
戻ったときに気付けない。** 判断はここに 1 つだけ置く。
"""

from __future__ import annotations

from typing import Optional


def span_text(ticks: int, minutes_per_tick: Optional[int]) -> str:
    """残りの長さを表す語を返す。先頭に空白が 1 つ入る。

    分に直せない世界では「手番 N 回ぶん」と書く。裸の数だけを置くと、個数にも
    識別子にも読める (#949 で地図が踏んだ形)。
    """
    if minutes_per_tick:
        return f" {ticks * minutes_per_tick} 分"
    return f" 手番 {ticks} 回ぶん"
