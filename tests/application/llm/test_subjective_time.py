"""主観時間ラベル v0 の検証 (Issue #526 不在 1: 時間軸の不在)。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ai_rpg_world.application.llm.services.subjective_time import (
    subjective_time_label,
    utc_now,
)


_NOW = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)


class TestSubjectiveTimeLabelBuckets:
    """now と occurred_at の差で日本語ラベルが決まる。"""

    def test_zero_delta_returns_tatta_ima(self) -> None:
        """delta=0 → "たった今"。"""
        assert subjective_time_label(_NOW, _NOW) == "たった今"

    def test_under_one_minute(self) -> None:
        """59 秒前は "たった今"。"""
        assert subjective_time_label(_NOW, _NOW - timedelta(seconds=59)) == "たった今"

    def test_a_few_minutes_ago(self) -> None:
        """1 分前 / 4 分前は "数分前"。"""
        assert subjective_time_label(_NOW, _NOW - timedelta(minutes=1)) == "数分前"
        assert subjective_time_label(_NOW, _NOW - timedelta(minutes=4, seconds=59)) == "数分前"

    def test_sakki(self) -> None:
        """5 分以上 30 分未満は "さっき"。"""
        assert subjective_time_label(_NOW, _NOW - timedelta(minutes=5)) == "さっき"
        assert subjective_time_label(_NOW, _NOW - timedelta(minutes=29)) == "さっき"

    def test_a_few_hours_ago(self) -> None:
        """30 分以上 4 時間未満は "数時間前"。"""
        assert subjective_time_label(_NOW, _NOW - timedelta(minutes=30)) == "数時間前"
        assert subjective_time_label(_NOW, _NOW - timedelta(hours=3)) == "数時間前"

    def test_today_label_for_same_day_more_than_4h(self) -> None:
        """4 時間以上前で同じ calendar day なら "今日のうち"。"""
        # 12:00 - 5h = 7:00 同日
        assert subjective_time_label(_NOW, _NOW - timedelta(hours=5)) == "今日のうち"

    def test_yesterday_label(self) -> None:
        """前日 (calendar day diff = 1) は "昨日"。"""
        assert subjective_time_label(_NOW, _NOW - timedelta(hours=18)) == "昨日"
        # 12:00 - 1 day = 同時刻でも calendar diff = 1
        assert subjective_time_label(_NOW, _NOW - timedelta(days=1)) == "昨日"

    def test_n_days_ago(self) -> None:
        """2 〜 6 日前は "{n}日前"。"""
        assert subjective_time_label(_NOW, _NOW - timedelta(days=2)) == "2日前"
        assert subjective_time_label(_NOW, _NOW - timedelta(days=6, hours=1)) == "6日前"

    def test_last_week(self) -> None:
        """7 〜 13 日前は "先週"。"""
        assert subjective_time_label(_NOW, _NOW - timedelta(days=7)) == "先週"
        assert subjective_time_label(_NOW, _NOW - timedelta(days=13)) == "先週"

    def test_long_ago(self) -> None:
        """14 日以上前は "ずっと前"。"""
        assert subjective_time_label(_NOW, _NOW - timedelta(days=14)) == "ずっと前"
        assert subjective_time_label(_NOW, _NOW - timedelta(days=365)) == "ずっと前"

    def test_future_returns_none(self) -> None:
        """occurred_at が now より未来なら None (ラベル付けない)。"""
        assert subjective_time_label(_NOW, _NOW + timedelta(minutes=1)) is None
        assert subjective_time_label(_NOW, _NOW + timedelta(days=2)) is None

    def test_under_4h_crossing_midnight_returns_hours_not_yesterday(self) -> None:
        """delta < 4h で日付をまたいでいても "数時間前" を優先する (delta 優先)。

        例: now=00:30(Day N), occurred_at=22:00(Day N-1)
        - delta = 2h30m < 4h → "数時間前"
        - calendar day diff = 1 (= "昨日" のはず) だがこちらは適用されない
        日本語の自然さ: 「2 時間前」の方が「昨日」より近距離を表すため。
        """
        now = datetime(2026, 6, 19, 0, 30, 0, tzinfo=timezone.utc)
        occ = datetime(2026, 6, 18, 22, 0, 0, tzinfo=timezone.utc)
        assert subjective_time_label(now, occ) == "数時間前"


class TestUtcNowHelper:
    """``utc_now`` の smoke。"""

    def test_returns_timezone_aware_utc(self) -> None:
        """tzinfo が UTC で返る。"""
        result = utc_now()
        assert result.tzinfo is timezone.utc


class TestSubjectiveTimeLabelNaiveDatetime:
    """naive datetime は UTC として扱われる。"""

    def test_naive_now_naive_occurred_at(self) -> None:
        """両方 naive でも比較できる。"""
        now_naive = datetime(2026, 6, 19, 12, 0, 0)
        past_naive = datetime(2026, 6, 18, 18, 0, 0)
        assert subjective_time_label(now_naive, past_naive) == "昨日"

    def test_aware_now_naive_occurred_at(self) -> None:
        """now が aware、occurred_at が naive でも UTC 解釈で揃う。"""
        now = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)
        past_naive = datetime(2026, 6, 18, 18, 0, 0)
        assert subjective_time_label(now, past_naive) == "昨日"
