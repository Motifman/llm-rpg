"""主観時間ラベル v0 (Issue #526 不在 1: 時間軸の不在に対する最小実装)。

「数分前」「今朝」「昨日」のような、now からの相対時間を日本語の自然な
語彙に変換する。

# 何を解くか

PR #531 (yesterday_v1 baseline) で、「直近の出来事」section に観測が
時系列ラベル無しで並ぶことが視覚化された:

    - 閲覧室で見習い司書の覚書を読んだ        ← 昨日のはず
    - 書架 A で『水』の断片語を見つけた        ← 昨日のはず
    - カイトの声: 「リン、昨日何してた?」      ← 今のこと

LLM 側からは「いま起きたばかり」と区別できず、narrative が崩れる。

# 設計

- ラベルは「now と occurred_at の差」の決定論的バケツマッピング
- バケツ境界は人間の語彙感に近づけて段階を粗くする (秒差で語彙が変わるのは不自然)
- 未来時刻 (= occurred_at > now) は None を返す (= ラベルを付けない)
- naive datetime は UTC として扱う (= sliding window / episode store と整合)
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional


def _normalize_to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def subjective_time_label(now: datetime, occurred_at: datetime) -> Optional[str]:
    """``now`` を基準にした ``occurred_at`` の主観時間ラベルを返す。

    バケツ:
      delta < 60s             → ``"たった今"``
      delta < 5min            → ``"数分前"``
      delta < 30min           → ``"さっき"``
      delta < 4h              → ``"数時間前"``
      same calendar day       → ``"今日のうち"`` (= 4h 以上前で同日)
      day_diff == 1           → ``"昨日"``
      2 <= day_diff < 7       → ``"{n}日前"``
      7 <= day_diff < 14      → ``"先週"``
      day_diff >= 14          → ``"ずっと前"``

    重要: **delta が先に評価される**。例えば ``now=00:30 (Day N)`` で
    ``occurred_at=22:00 (Day N-1)`` の場合、calendar day diff は 1 だが
    delta は 2.5h なので ``"昨日"`` ではなく ``"数時間前"`` を返す。
    人間が日本語で「2 時間前」と言う方が「昨日」と言うより自然な短さ
    だという判断 (= "昨日" は丸 1 日近い距離感を含意する)。

    ``occurred_at`` が ``now`` より未来なら ``None`` (= ラベル付けない)。

    naive datetime は UTC として正規化される (= sliding window /
    episode store の他のヘルパと挙動を揃える)。
    """
    n = _normalize_to_utc(now)
    o = _normalize_to_utc(occurred_at)
    delta = n - o
    if delta < timedelta(0):
        return None
    if delta < timedelta(seconds=60):
        return "たった今"
    if delta < timedelta(minutes=5):
        return "数分前"
    if delta < timedelta(minutes=30):
        return "さっき"
    if delta < timedelta(hours=4):
        return "数時間前"
    day_diff = (n.date() - o.date()).days
    if day_diff == 0:
        return "今日のうち"
    if day_diff == 1:
        return "昨日"
    if day_diff < 7:
        return f"{day_diff}日前"
    if day_diff < 14:
        return "先週"
    return "ずっと前"


def utc_now() -> datetime:
    """wall-clock UTC の現在時刻。wiring 側で ``time_provider=utc_now`` と
    渡すための canonical な provider。
    """
    return datetime.now(timezone.utc)


__all__ = ["subjective_time_label", "utc_now"]
