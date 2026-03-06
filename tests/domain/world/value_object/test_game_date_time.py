"""GameDateTime と game_date_time_from_tick のテスト（正常・境界・例外）"""

import pytest
from ai_rpg_world.domain.world.value_object.game_date_time import (
    GameDateTime,
    game_date_time_from_tick,
)


class TestGameDateTime:
    """GameDateTime 値オブジェクトのテスト"""

    def test_create_valid_values(self):
        """正常な年・月・日・時・分・秒で生成できること"""
        dt = GameDateTime(
            year=1, month=1, day=1,
            hour=0, minute=0, second=0,
        )
        assert dt.year == 1 and dt.month == 1 and dt.day == 1
        assert dt.hour == 0 and dt.minute == 0 and dt.second == 0

    def test_format_for_display(self):
        """format_for_display が期待どおりの文字列を返すこと"""
        dt = GameDateTime(
            year=2, month=3, day=4,
            hour=12, minute=30, second=45,
        )
        assert dt.format_for_display() == "2年3月4日 12:30:45"

    def test_format_for_display_zero_padding(self):
        """時・分・秒がゼロ埋めで表示されること"""
        dt = GameDateTime(
            year=1, month=1, day=1,
            hour=1, minute=2, second=3,
        )
        assert dt.format_for_display() == "1年1月1日 01:02:03"

    def test_year_positive_required(self):
        """year が 1 未満のとき ValueError"""
        with pytest.raises(ValueError, match="year must be positive"):
            GameDateTime(
                year=0, month=1, day=1,
                hour=0, minute=0, second=0,
            )

    def test_month_positive_required(self):
        """month が 1 未満のとき ValueError"""
        with pytest.raises(ValueError, match="month must be positive"):
            GameDateTime(
                year=1, month=0, day=1,
                hour=0, minute=0, second=0,
            )

    def test_day_positive_required(self):
        """day が 1 未満のとき ValueError"""
        with pytest.raises(ValueError, match="day must be positive"):
            GameDateTime(
                year=1, month=1, day=0,
                hour=0, minute=0, second=0,
            )

    def test_hour_range_0_to_23(self):
        """hour が 0-23 の範囲外のとき ValueError"""
        with pytest.raises(ValueError, match="hour must be 0-23"):
            GameDateTime(
                year=1, month=1, day=1,
                hour=24, minute=0, second=0,
            )
        with pytest.raises(ValueError, match="hour must be 0-23"):
            GameDateTime(
                year=1, month=1, day=1,
                hour=-1, minute=0, second=0,
            )

    def test_minute_range_0_to_59(self):
        """minute が 0-59 の範囲外のとき ValueError"""
        with pytest.raises(ValueError, match="minute must be 0-59"):
            GameDateTime(
                year=1, month=1, day=1,
                hour=0, minute=60, second=0,
            )

    def test_second_range_0_to_59(self):
        """second が 0-59 の範囲外のとき ValueError"""
        with pytest.raises(ValueError, match="second must be 0-59"):
            GameDateTime(
                year=1, month=1, day=1,
                hour=0, minute=0, second=60,
            )


class TestGameDateTimeFromTick:
    """game_date_time_from_tick 純粋関数のテスト"""

    def test_ticks_per_day_positive_required(self):
        """ticks_per_day が 1 未満のとき ValueError"""
        with pytest.raises(ValueError, match="ticks_per_day must be positive"):
            game_date_time_from_tick(0, 0)
        with pytest.raises(ValueError, match="ticks_per_day must be positive"):
            game_date_time_from_tick(0, -1)

    def test_days_per_month_positive_required(self):
        """days_per_month が 1 未満のとき ValueError"""
        with pytest.raises(ValueError, match="days_per_month must be positive"):
            game_date_time_from_tick(0, 86400, days_per_month=0)

    def test_months_per_year_positive_required(self):
        """months_per_year が 1 未満のとき ValueError"""
        with pytest.raises(ValueError, match="months_per_year must be positive"):
            game_date_time_from_tick(0, 86400, months_per_year=0)

    def test_tick_zero_first_moment(self):
        """tick=0 は 1年1月1日 00:00:00 になること"""
        dt = game_date_time_from_tick(
            0, ticks_per_day=86400,
            days_per_month=30, months_per_year=12,
        )
        assert dt.year == 1 and dt.month == 1 and dt.day == 1
        assert dt.hour == 0 and dt.minute == 0 and dt.second == 0

    def test_one_day_advances_calendar(self):
        """1日分のティックで日付が 1 日進むこと（1日=86400ティック）"""
        dt0 = game_date_time_from_tick(0, 86400)
        dt1 = game_date_time_from_tick(86400, 86400)
        assert dt0.year == 1 and dt0.month == 1 and dt0.day == 1
        assert dt1.year == 1 and dt1.month == 1 and dt1.day == 2

    def test_time_within_day_maps_to_clock(self):
        """1日以内のティックが時・分・秒に正しくマップされること"""
        # 86400 ticks/day → 1 tick = 1 second
        # tick 3600 = 1:00:00
        dt = game_date_time_from_tick(3600, 86400)
        assert dt.hour == 1 and dt.minute == 0 and dt.second == 0
        # tick 3661 = 1:01:01
        dt2 = game_date_time_from_tick(3661, 86400)
        assert dt2.hour == 1 and dt2.minute == 1 and dt2.second == 1

    def test_fewer_ticks_per_day_still_maps_seconds(self):
        """1日のティック数が少なくても 1 日を 86400 秒にマップすること"""
        # 96 ticks/day: 1 tick = 900 sec. tick 0 → 0:00:00, tick 1 → 0:15:00
        dt = game_date_time_from_tick(1, 96)
        assert dt.hour == 0 and dt.minute == 15 and dt.second == 0
        # tick 4 → 1:00:00
        dt2 = game_date_time_from_tick(4, 96)
        assert dt2.hour == 1 and dt2.minute == 0 and dt2.second == 0

    def test_month_rollover(self):
        """日が days_per_month を超えると月が繰り上がること"""
        # 30日/月: 0日目=1/1, 29日目=1/30, 30日目=2/1
        ticks_per_day = 86400
        days_per_month = 30
        dt_day29 = game_date_time_from_tick(
            29 * ticks_per_day, ticks_per_day,
            days_per_month=days_per_month, months_per_year=12,
        )
        assert dt_day29.month == 1 and dt_day29.day == 30
        dt_day30 = game_date_time_from_tick(
            30 * ticks_per_day, ticks_per_day,
            days_per_month=days_per_month, months_per_year=12,
        )
        assert dt_day30.month == 2 and dt_day30.day == 1

    def test_year_rollover(self):
        """日が 1 年分を超えると年が繰り上がること（360日=12*30）"""
        ticks_per_day = 86400
        days_per_month = 30
        months_per_year = 12
        days_per_year = days_per_month * months_per_year  # 360
        dt_last_day_year1 = game_date_time_from_tick(
            (days_per_year - 1) * ticks_per_day,
            ticks_per_day,
            days_per_month=days_per_month,
            months_per_year=months_per_year,
        )
        assert dt_last_day_year1.year == 1 and dt_last_day_year1.month == 12 and dt_last_day_year1.day == 30
        dt_first_day_year2 = game_date_time_from_tick(
            days_per_year * ticks_per_day,
            ticks_per_day,
            days_per_month=days_per_month,
            months_per_year=months_per_year,
        )
        assert dt_first_day_year2.year == 2 and dt_first_day_year2.month == 1 and dt_first_day_year2.day == 1

    def test_negative_tick_treated_as_zero(self):
        """負のティックは 0 として扱うこと"""
        dt = game_date_time_from_tick(-100, 86400)
        assert dt.year == 1 and dt.month == 1 and dt.day == 1
        assert dt.hour == 0 and dt.minute == 0 and dt.second == 0
